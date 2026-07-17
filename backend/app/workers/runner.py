from __future__ import annotations

import asyncio
import logging
import os
import socket
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.enums import JobStatus, JobType, SourceStatus
from app.db.base import utc_now
from app.db.models.operations import Job, Source, SourceSyncState
from app.db.repositories.jobs import (
    cancel_job,
    claim_next_job,
    complete_job,
    fail_job,
    heartbeat_job,
    heartbeat_worker_instance,
    mark_worker_stopping,
    recover_stale_jobs,
    register_worker_instance,
    requeue_job,
    stop_worker_instance,
)
from app.workers.source_sync import HandlerOutcome, SourceSyncHandler

logger = logging.getLogger("pyanswer.worker")


class WorkerRunner:
    SUPPORTED_TYPES = frozenset({JobType.SOURCE_SYNC})

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        instance_id: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._instance_id = instance_id or (f"{socket.gethostname()}:{os.getpid()}:{uuid4()}")
        self._worker_id: UUID | None = None
        self._current_job_id: UUID | None = None
        self._shutdown_requested = asyncio.Event()
        self._heartbeat_stop = asyncio.Event()

    @property
    def worker_id(self) -> UUID | None:
        return self._worker_id

    def request_shutdown(self) -> None:
        self._shutdown_requested.set()

    async def start(self) -> None:
        if self._worker_id is None:
            await self._register()

    async def process_once(self, http_client: httpx.AsyncClient) -> UUID | None:
        await self.start()
        await self._recover_stale()
        job_id = await self._claim()
        if job_id is None:
            await self._heartbeat_once()
            return None
        self._current_job_id = job_id
        try:
            await self._heartbeat_once()
            await self._execute_job(job_id, http_client)
        finally:
            self._current_job_id = None
        await self._heartbeat_once()
        return job_id

    async def close(self) -> None:
        if self._worker_id is None:
            return
        await self._mark_stopping()
        await self._stop()

    async def run(self) -> None:
        await self.start()
        timeout = httpx.Timeout(
            connect=self._settings.stackexchange_connect_timeout_seconds,
            read=self._settings.stackexchange_read_timeout_seconds,
            write=self._settings.stackexchange_write_timeout_seconds,
            pool=self._settings.stackexchange_pool_timeout_seconds,
        )
        async with httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": self._settings.stackexchange_user_agent},
            follow_redirects=False,
        ) as http_client:
            heartbeat_task = asyncio.create_task(
                self._heartbeat_loop(),
                name="pyanswer-worker-heartbeat",
            )
            try:
                while not self._shutdown_requested.is_set():
                    job_id = await self.process_once(http_client)
                    if job_id is None:
                        await self._wait_for_poll()
            finally:
                self._heartbeat_stop.set()
                await heartbeat_task
                await self.close()

    async def _register(self) -> None:
        async with self._session_factory() as session, session.begin():
            worker = await register_worker_instance(
                session,
                name="PyAnswer ingestion worker",
                instance_id=self._instance_id,
                capabilities={"source_sync", "document_reprocess"},
                version=self._settings.app_version,
                hostname=socket.gethostname(),
                pid=os.getpid(),
            )
            self._worker_id = worker.id

    async def _claim(self) -> UUID | None:
        worker_id = self._require_worker_id()
        async with self._session_factory() as session, session.begin():
            job = await claim_next_job(
                session,
                worker_id=worker_id,
                supported_types=self.SUPPORTED_TYPES,
                lease_seconds=self._settings.worker_lease_seconds,
            )
            if job is None:
                return None
            if job.source_id is not None:
                source = await session.get(Source, job.source_id, with_for_update=True)
                if source is not None:
                    source.status = SourceStatus.SYNCING
                    source.current_job_id = job.id
            return job.id

    async def _execute_job(self, job_id: UUID, http_client: httpx.AsyncClient) -> None:
        worker_id = self._require_worker_id()
        try:
            outcome = await SourceSyncHandler(
                session_factory=self._session_factory,
                settings=self._settings,
                http_client=http_client,
                job_id=job_id,
                worker_id=worker_id,
                shutdown_requested=self._shutdown_requested,
            ).run()
        except Exception:
            logger.exception("worker_handler_failed", extra={"jobId": str(job_id)})
            outcome = HandlerOutcome(
                "FAILED",
                error_code="INTERNAL_HANDLER_ERROR",
                error_message="Внутренняя ошибка обработчика фонового задания",
            )
        await self._finalize(job_id, outcome)

    async def _finalize(self, job_id: UUID, outcome: HandlerOutcome) -> None:
        worker_id = self._require_worker_id()
        async with self._session_factory() as session, session.begin():
            job: Job | None
            if outcome.disposition == "COMPLETED":
                job = await complete_job(
                    session,
                    job_id=job_id,
                    worker_id=worker_id,
                    result=outcome.result,
                )
            elif outcome.disposition == "CANCELLED":
                job = await cancel_job(session, job_id=job_id, worker_id=worker_id)
            elif outcome.disposition == "REQUEUED":
                job = await requeue_job(
                    session,
                    job_id=job_id,
                    worker_id=worker_id,
                    next_attempt_at=outcome.next_attempt_at or utc_now() + timedelta(minutes=5),
                    error_code=outcome.error_code or "RETRY_SCHEDULED",
                    error_message=outcome.error_message or "Повтор задания запланирован",
                )
            else:
                job = await fail_job(
                    session,
                    job_id=job_id,
                    worker_id=worker_id,
                    error_code=outcome.error_code or "JOB_FAILED",
                    error_message=outcome.error_message or "Фоновое задание завершилось ошибкой",
                    result=outcome.result,
                )
            if job is not None and job.source_id is not None:
                source = await session.get(Source, job.source_id, with_for_update=True)
                if source is not None:
                    self._update_source_after_job(source, job)
                    await self._update_sync_completion(session, source, job)

    @staticmethod
    def _update_source_after_job(source: Source, job: Job) -> None:
        if job.status == JobStatus.COMPLETED:
            source.status = SourceStatus.IDLE
            source.current_job_id = None
            source.last_error = None
            source.last_sync_at = job.finished_at
        elif job.status == JobStatus.CANCELLED:
            source.status = SourceStatus.PAUSED
            source.current_job_id = None
            source.last_error = "Синхронизация отменена"
        elif job.status == JobStatus.FAILED:
            source.status = SourceStatus.ERROR
            source.current_job_id = None
            source.last_error = job.error_message
        elif job.status == JobStatus.QUEUED:
            source.status = SourceStatus.PAUSED
            source.current_job_id = job.id
            source.last_error = job.error_message

    @staticmethod
    async def _update_sync_completion(
        session: AsyncSession,
        source: Source,
        job: Job,
    ) -> None:
        if job.status != JobStatus.COMPLETED or job.type != JobType.SOURCE_SYNC:
            return
        dry_run = job.result.get("dryRun") is True
        if dry_run:
            return
        source.last_successful_sync_at = job.finished_at
        state = await session.get(SourceSyncState, source.id, with_for_update=True)
        if state is None:
            return
        if job.result.get("syncComplete") is not True:
            return
        fixed_todate = job.result.get("fixedTodate")
        if type(fixed_todate) is not int or fixed_todate < 0:
            return
        completed_at = job.finished_at or utc_now()
        mode = job.result.get("mode")
        if mode == "INITIAL":
            state.initial_sync_completed_at = completed_at
        elif mode == "INCREMENTAL":
            state.incremental_watermark = datetime.fromtimestamp(fixed_todate, UTC)
        state.next_page = 1
        state.current_mode = None
        state.state = {
            "fixedTodate": fixed_todate,
            "itemOffset": 0,
            "completedAt": completed_at.isoformat(),
        }

    async def _heartbeat_loop(self) -> None:
        while not self._heartbeat_stop.is_set():
            await self._heartbeat_once()
            try:
                await asyncio.wait_for(
                    self._heartbeat_stop.wait(),
                    timeout=self._settings.worker_heartbeat_seconds,
                )
            except TimeoutError:
                continue

    async def _heartbeat_once(self) -> None:
        worker_id = self._require_worker_id()
        async with self._session_factory() as session, session.begin():
            if self._current_job_id is not None:
                await heartbeat_job(
                    session,
                    job_id=self._current_job_id,
                    worker_id=worker_id,
                    lease_seconds=self._settings.worker_lease_seconds,
                )
            else:
                await heartbeat_worker_instance(session, worker_id=worker_id)

    async def _recover_stale(self) -> None:
        async with self._session_factory() as session, session.begin():
            result = await recover_stale_jobs(
                session,
                retry_delay_seconds=round(self._settings.worker_poll_interval_seconds),
            )
            terminal_ids = (*result.failed_job_ids, *result.cancelled_job_ids)
            for job_id in terminal_ids:
                job = await session.get(Job, job_id)
                if job is None or job.source_id is None:
                    continue
                source = await session.get(Source, job.source_id, with_for_update=True)
                if source is not None and source.current_job_id == job.id:
                    source.current_job_id = None
                    source.status = (
                        SourceStatus.ERROR
                        if job.status == JobStatus.FAILED
                        else SourceStatus.PAUSED
                    )
                    source.last_error = job.error_message
            for job_id in result.requeued_job_ids:
                job = await session.get(Job, job_id)
                if job is None or job.source_id is None:
                    continue
                source = await session.get(Source, job.source_id, with_for_update=True)
                if source is not None:
                    source.current_job_id = job.id
                    source.status = SourceStatus.PAUSED
                    source.last_error = job.error_message

    async def _wait_for_poll(self) -> None:
        try:
            await asyncio.wait_for(
                self._shutdown_requested.wait(),
                timeout=self._settings.worker_poll_interval_seconds,
            )
        except TimeoutError:
            return

    async def _mark_stopping(self) -> None:
        async with self._session_factory() as session, session.begin():
            await mark_worker_stopping(session, worker_id=self._require_worker_id())

    async def _stop(self) -> None:
        async with self._session_factory() as session, session.begin():
            await stop_worker_instance(session, worker_id=self._require_worker_id())

    def _require_worker_id(self) -> UUID:
        if self._worker_id is None:
            raise RuntimeError("Worker instance ещё не зарегистрирован")
        return self._worker_id
