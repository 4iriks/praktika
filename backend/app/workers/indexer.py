from __future__ import annotations

import asyncio
import logging
import os
import socket
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.enums import JobType
from app.db.base import utc_now
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
from app.integrations.embeddings import OllamaEmbeddingProvider
from app.integrations.qdrant import (
    QdrantIndexClient,
    index_schema_from_settings,
    sparse_provider_from_settings,
)
from app.services.search_index import SearchIndexJobHandler
from app.workers.source_sync import HandlerOutcome

logger = logging.getLogger("pyanswer.indexer")


class IndexerRunner:
    SUPPORTED_TYPES = frozenset(
        {
            JobType.DOCUMENT_REINDEX,
            JobType.FULL_REINDEX,
            JobType.SEARCH_INDEX_VALIDATE,
            JobType.SEARCH_INDEX_CLEANUP,
        }
    )

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        instance_id: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._instance_id = instance_id or f"indexer:{socket.gethostname()}:{os.getpid()}:{uuid4()}"
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
            async with self._session_factory() as session, session.begin():
                worker = await register_worker_instance(
                    session,
                    name="PyAnswer search indexer",
                    instance_id=self._instance_id,
                    capabilities={
                        "search_index",
                        "document_reindex",
                        "full_reindex",
                        "search_index_cleanup",
                        "search_index_validate",
                    },
                    version=self._settings.app_version,
                    hostname=socket.gethostname(),
                    pid=os.getpid(),
                )
                self._worker_id = worker.id

    async def process_once(
        self,
        *,
        embeddings: OllamaEmbeddingProvider,
        qdrant: QdrantIndexClient,
    ) -> UUID | None:
        await self.start()
        await self._recover_stale()
        job_id = await self._claim()
        if job_id is None:
            await self._heartbeat_once()
            return None
        self._current_job_id = job_id
        try:
            await self._heartbeat_once()
            await self._execute_job(job_id, embeddings=embeddings, qdrant=qdrant)
        finally:
            self._current_job_id = None
        await self._heartbeat_once()
        return job_id

    async def run(self) -> None:
        await self.start()
        embeddings = OllamaEmbeddingProvider(self._settings, cancellation=self._shutdown_requested)
        qdrant = QdrantIndexClient(self._settings, cancellation=self._shutdown_requested)
        heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(), name="pyanswer-indexer-heartbeat"
        )
        try:
            while not self._shutdown_requested.is_set():
                job_id = await self.process_once(embeddings=embeddings, qdrant=qdrant)
                if job_id is None:
                    await self._wait_for_poll()
        finally:
            self._heartbeat_stop.set()
            await heartbeat_task
            await embeddings.close()
            await qdrant.close()
            await self.close()

    async def close(self) -> None:
        if self._worker_id is None:
            return
        async with self._session_factory() as session, session.begin():
            await mark_worker_stopping(session, worker_id=self._worker_id)
        async with self._session_factory() as session, session.begin():
            await stop_worker_instance(session, worker_id=self._worker_id)

    async def _claim(self) -> UUID | None:
        async with self._session_factory() as session, session.begin():
            job = await claim_next_job(
                session,
                worker_id=self._require_worker_id(),
                supported_types=self.SUPPORTED_TYPES,
                lease_seconds=self._settings.worker_lease_seconds,
            )
            return job.id if job is not None else None

    async def _execute_job(
        self,
        job_id: UUID,
        *,
        embeddings: OllamaEmbeddingProvider,
        qdrant: QdrantIndexClient,
    ) -> None:
        try:
            outcome = await SearchIndexJobHandler(
                session_factory=self._session_factory,
                settings=self._settings,
                schema=index_schema_from_settings(self._settings),
                embeddings=embeddings,
                sparse=sparse_provider_from_settings(self._settings),
                qdrant=qdrant,
                job_id=job_id,
                worker_id=self._require_worker_id(),
                shutdown_requested=self._shutdown_requested,
            ).run()
        except (RuntimeError, ValueError):
            logger.exception("indexer_handler_failed", extra={"jobId": str(job_id)})
            outcome = HandlerOutcome(
                "FAILED",
                error_code="INTERNAL_INDEXER_ERROR",
                error_message="Внутренняя ошибка indexer worker",
            )
        await self._finalize(job_id, outcome)

    async def _finalize(self, job_id: UUID, outcome: HandlerOutcome) -> None:
        worker_id = self._require_worker_id()
        async with self._session_factory() as session, session.begin():
            if outcome.disposition == "COMPLETED":
                await complete_job(
                    session, job_id=job_id, worker_id=worker_id, result=outcome.result
                )
            elif outcome.disposition == "CANCELLED":
                await cancel_job(session, job_id=job_id, worker_id=worker_id)
            elif outcome.disposition == "REQUEUED":
                await requeue_job(
                    session,
                    job_id=job_id,
                    worker_id=worker_id,
                    next_attempt_at=outcome.next_attempt_at or utc_now() + timedelta(minutes=1),
                    error_code=outcome.error_code or "INDEX_RETRY_SCHEDULED",
                    error_message=outcome.error_message or "Повтор индексации запланирован",
                )
            else:
                await fail_job(
                    session,
                    job_id=job_id,
                    worker_id=worker_id,
                    error_code=outcome.error_code or "INDEX_JOB_FAILED",
                    error_message=outcome.error_message or "Индексация завершилась ошибкой",
                    result=outcome.result,
                )

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
        async with self._session_factory() as session, session.begin():
            await heartbeat_worker_instance(session, worker_id=self._require_worker_id())
            if self._current_job_id is not None:
                await heartbeat_job(
                    session,
                    job_id=self._current_job_id,
                    worker_id=self._require_worker_id(),
                    lease_seconds=self._settings.worker_lease_seconds,
                )

    async def _recover_stale(self) -> None:
        async with self._session_factory() as session, session.begin():
            await recover_stale_jobs(
                session,
                retry_delay_seconds=round(self._settings.worker_poll_interval_seconds),
            )

    async def _wait_for_poll(self) -> None:
        try:
            await asyncio.wait_for(
                self._shutdown_requested.wait(),
                timeout=self._settings.worker_poll_interval_seconds,
            )
        except TimeoutError:
            return

    def _require_worker_id(self) -> UUID:
        if self._worker_id is None:
            raise RuntimeError("Indexer instance ещё не зарегистрирован")
        return self._worker_id
