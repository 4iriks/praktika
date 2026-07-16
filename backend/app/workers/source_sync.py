from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

import httpx
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.enums import JobEventLevel, JobStage, JobStatus, SourceSyncMode
from app.db.base import utc_now
from app.db.models.operations import Job, Source, SourceSyncState
from app.db.repositories.jobs import add_job_event, update_job_progress
from app.integrations.stackexchange.client import StackExchangeClient
from app.integrations.stackexchange.errors import (
    StackExchangeCancelled,
    StackExchangeClientError,
    StackExchangeQuotaLow,
)
from app.integrations.stackexchange.schemas import StackExchangeResponseMetrics
from app.schemas.base import ApiModel


class SourceSyncJobPayload(ApiModel):
    source_id: UUID
    mode: SourceSyncMode = SourceSyncMode.AUTO
    max_documents: int | None = None
    max_pages: int | None = None
    dry_run: bool = False


@dataclass(frozen=True, slots=True)
class HandlerOutcome:
    disposition: Literal["COMPLETED", "FAILED", "REQUEUED", "CANCELLED"]
    result: dict[str, object] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    next_attempt_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SourceSyncContext:
    source_id: UUID
    source_page_size: int
    target_documents: int
    mode: SourceSyncMode
    initial_completed: bool
    incremental_watermark: datetime | None
    checkpoint: dict[str, object]
    initial_request_count: int
    initial_bytes_received: int


@dataclass(slots=True)
class RuntimeCounters:
    questions: int
    answers: int
    requests: int
    bytes_received: int
    pages: int


class WorkerJobLost(RuntimeError):
    """The worker no longer owns the job lease."""


class InvalidSourceSyncPayload(RuntimeError):
    """The durable job payload does not match its source reference."""


class SourceSyncHandler:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        http_client: httpx.AsyncClient,
        job_id: UUID,
        worker_id: UUID,
        shutdown_requested: asyncio.Event,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._http_client = http_client
        self._job_id = job_id
        self._worker_id = worker_id
        self._shutdown_requested = shutdown_requested
        self._counters = RuntimeCounters(0, 0, 0, 0, 0)

    async def run(self) -> HandlerOutcome:
        try:
            payload, context = await self._load_context()
        except (ValidationError, InvalidSourceSyncPayload):
            return HandlerOutcome(
                "FAILED",
                error_code="INVALID_JOB_PAYLOAD",
                error_message="Payload SOURCE_SYNC не прошёл валидацию",
            )
        if not payload.dry_run:
            return HandlerOutcome(
                "FAILED",
                error_code="HANDLER_NOT_READY",
                error_message="Полная обработка SOURCE_SYNC будет включена в подэтапе 5.2",
            )

        self._counters.requests = context.initial_request_count
        self._counters.bytes_received = context.initial_bytes_received
        self._counters.questions = _checkpoint_int(context.checkpoint, "questionsFetched")
        self._counters.answers = _checkpoint_int(context.checkpoint, "answersFetched")
        start_page = max(1, _checkpoint_int(context.checkpoint, "currentPage", default=1))
        fixed_todate = _checkpoint_int(
            context.checkpoint,
            "fixedTodate",
            default=round(utc_now().timestamp()),
        )
        max_documents = payload.max_documents or 200
        max_pages = payload.max_pages or 2
        mode = self._resolve_mode(payload.mode, context.initial_completed)
        fromdate: int | None = None
        if mode == SourceSyncMode.INCREMENTAL and context.incremental_watermark is not None:
            fromdate = max(
                0,
                round(context.incremental_watermark.timestamp())
                - self._settings.stackexchange_incremental_overlap_seconds,
            )
        sort = "creation" if mode == SourceSyncMode.INITIAL else "activity"

        try:
            await self._set_source_syncing(mode)
            async with StackExchangeClient(
                self._settings,
                client=self._http_client,
                cancellation_check=self._is_cancelled,
                on_metrics=self._record_response_metrics,
                on_event=self._record_client_event,
            ) as client:
                async for page in client.iterate_questions(
                    sort=sort,
                    start_page=start_page,
                    fromdate=fromdate,
                    todate=fixed_todate,
                    page_size=context.source_page_size,
                    max_pages=max_pages,
                ):
                    if await self._is_cancelled():
                        raise StackExchangeCancelled
                    remaining = max_documents - self._counters.questions
                    if remaining <= 0:
                        break
                    questions = page.envelope.items[:remaining]
                    await self._record_page_event(
                        JobStage.FETCHING_QUESTIONS,
                        "QUESTIONS_PAGE_FETCHED",
                        "Получена страница вопросов Stack Exchange",
                        {"page": page.page, "items": len(questions)},
                    )
                    await self._set_stage(JobStage.FETCHING_ANSWERS)
                    answers_in_batch = 0
                    question_ids = [item.question_id for item in questions]
                    if question_ids:
                        async for answer_page in client.fetch_answers_for_question_ids(
                            question_ids,
                            max_pages=self._settings.stackexchange_max_pages,
                        ):
                            answers_in_batch += len(answer_page.envelope.items)
                    self._counters.questions += len(questions)
                    self._counters.answers += answers_in_batch
                    self._counters.pages += 1
                    await self._record_page_event(
                        JobStage.FETCHING_ANSWERS,
                        "ANSWERS_BATCH_FETCHED",
                        "Получены страницы ответов для пакета вопросов",
                        {
                            "page": page.page,
                            "questions": len(questions),
                            "answers": answers_in_batch,
                        },
                    )
                    await self._save_dry_run_checkpoint(
                        mode=mode,
                        fixed_todate=fixed_todate,
                        current_page=page.page + 1,
                        max_documents=max_documents,
                        max_pages=max_pages,
                    )
                    if self._counters.questions >= max_documents:
                        break
        except StackExchangeCancelled:
            if await self._has_user_cancellation():
                return HandlerOutcome("CANCELLED", result=self._result(mode, start_page))
            return HandlerOutcome(
                "REQUEUED",
                result=self._result(mode, start_page),
                error_code="WORKER_SHUTDOWN",
                error_message="Worker завершает работу после безопасного checkpoint",
                next_attempt_at=utc_now() + timedelta(seconds=5),
            )
        except StackExchangeQuotaLow as exc:
            return HandlerOutcome(
                "REQUEUED",
                result=self._result(mode, start_page),
                error_code=exc.code,
                error_message=exc.safe_message,
                next_attempt_at=utc_now() + timedelta(hours=1),
            )
        except StackExchangeClientError as exc:
            if exc.retryable:
                return HandlerOutcome(
                    "REQUEUED",
                    result=self._result(mode, start_page),
                    error_code=exc.code,
                    error_message=exc.safe_message,
                    next_attempt_at=utc_now() + timedelta(minutes=5),
                )
            return HandlerOutcome(
                "FAILED",
                result=self._result(mode, start_page),
                error_code=exc.code,
                error_message=exc.safe_message,
            )

        return HandlerOutcome("COMPLETED", result=self._result(mode, start_page))

    async def _load_context(self) -> tuple[SourceSyncJobPayload, SourceSyncContext]:
        async with self._session_factory() as session:
            job = await session.get(Job, self._job_id)
            if job is None or job.claimed_by != self._worker_id or job.status != JobStatus.RUNNING:
                raise WorkerJobLost("SOURCE_SYNC job больше не принадлежит worker")
            payload = SourceSyncJobPayload.model_validate(job.payload)
            source = await session.get(Source, payload.source_id)
            if source is None or job.source_id != source.id:
                raise InvalidSourceSyncPayload
            state = await session.get(SourceSyncState, source.id)
            return payload, SourceSyncContext(
                source_id=source.id,
                source_page_size=min(source.page_size, self._settings.stackexchange_page_size),
                target_documents=source.target_documents,
                mode=payload.mode,
                initial_completed=bool(state and state.initial_sync_completed_at),
                incremental_watermark=state.incremental_watermark if state else None,
                checkpoint=dict(job.checkpoint),
                initial_request_count=job.request_count,
                initial_bytes_received=job.bytes_received,
            )

    @staticmethod
    def _resolve_mode(requested: SourceSyncMode, initial_completed: bool) -> SourceSyncMode:
        if requested != SourceSyncMode.AUTO:
            return requested
        return SourceSyncMode.INCREMENTAL if initial_completed else SourceSyncMode.INITIAL

    async def _is_cancelled(self) -> bool:
        if self._shutdown_requested.is_set():
            return True
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(Job.status, Job.cancellation_requested_at).where(Job.id == self._job_id)
                )
            ).one_or_none()
        return row is None or row[0] != JobStatus.RUNNING or row[1] is not None

    async def _has_user_cancellation(self) -> bool:
        async with self._session_factory() as session:
            job = await session.get(Job, self._job_id)
            return bool(job and job.cancellation_requested_at is not None)

    async def _set_source_syncing(self, mode: SourceSyncMode) -> None:
        async with self._session_factory() as session, session.begin():
            job = await update_job_progress(
                session,
                job_id=self._job_id,
                worker_id=self._worker_id,
                stage=JobStage.FETCHING_QUESTIONS,
            )
            if job is None:
                raise WorkerJobLost("SOURCE_SYNC job lease потерян")
            source = await session.get(Source, job.source_id, with_for_update=True)
            if source is not None:
                source.status = "SYNCING"
                source.last_error = None
            await add_job_event(
                session,
                job_id=self._job_id,
                level=JobEventLevel.INFO,
                stage=JobStage.FETCHING_QUESTIONS,
                code="DRY_RUN_SYNC_STARTED",
                message="Запущена ограниченная проверка Stack Exchange без сохранения документов",
                metrics={"mode": mode.value},
            )

    async def _set_stage(self, stage: JobStage) -> None:
        async with self._session_factory() as session, session.begin():
            job = await update_job_progress(
                session,
                job_id=self._job_id,
                worker_id=self._worker_id,
                stage=stage,
            )
            if job is None:
                raise WorkerJobLost("SOURCE_SYNC job lease потерян")

    async def _record_response_metrics(self, metrics: StackExchangeResponseMetrics) -> None:
        self._counters.requests += 1
        self._counters.bytes_received += metrics.response_bytes
        async with self._session_factory() as session, session.begin():
            job = await update_job_progress(
                session,
                job_id=self._job_id,
                worker_id=self._worker_id,
                request_count_delta=1,
                bytes_received_delta=metrics.response_bytes,
            )
            if job is None:
                raise WorkerJobLost("SOURCE_SYNC job lease потерян")
            source = await session.get(Source, job.source_id, with_for_update=True)
            if source is not None:
                if metrics.quota_remaining is not None:
                    source.rate_limit_remaining = metrics.quota_remaining
                if metrics.quota_max is not None:
                    source.rate_limit_total = metrics.quota_max
                source.rate_limit_updated_at = utc_now()
                source.api_key_configured = self._settings.stackexchange_key is not None

    async def _record_client_event(
        self,
        code: str,
        message: str,
        metrics: Mapping[str, object],
    ) -> None:
        async with self._session_factory() as session, session.begin():
            job = await session.get(Job, self._job_id, with_for_update=True)
            if job is None:
                raise WorkerJobLost("SOURCE_SYNC job отсутствует")
            stage = (
                JobStage.WAITING_BACKOFF
                if code in {"STACKEXCHANGE_BACKOFF", "STACKEXCHANGE_RETRY"}
                else JobStage(job.stage)
            )
            job.stage = stage
            await add_job_event(
                session,
                job_id=self._job_id,
                level=JobEventLevel.WARNING,
                stage=stage,
                code=code,
                message=message,
                metrics=metrics,
            )

    async def _record_page_event(
        self,
        stage: JobStage,
        code: str,
        message: str,
        metrics: dict[str, object],
    ) -> None:
        async with self._session_factory() as session, session.begin():
            job = await update_job_progress(
                session,
                job_id=self._job_id,
                worker_id=self._worker_id,
                stage=stage,
            )
            if job is None:
                raise WorkerJobLost("SOURCE_SYNC job lease потерян")
            await add_job_event(
                session,
                job_id=self._job_id,
                level=JobEventLevel.INFO,
                stage=stage,
                code=code,
                message=message,
                metrics=metrics,
            )

    async def _save_dry_run_checkpoint(
        self,
        *,
        mode: SourceSyncMode,
        fixed_todate: int,
        current_page: int,
        max_documents: int,
        max_pages: int,
    ) -> None:
        progress = min(
            99,
            max(
                round(self._counters.questions / max_documents * 100),
                round(self._counters.pages / max_pages * 100),
            ),
        )
        checkpoint: dict[str, object] = {
            "dryRun": True,
            "mode": mode.value,
            "fixedTodate": fixed_todate,
            "currentPage": current_page,
            "lastSuccessfulPage": current_page - 1,
            "questionsFetched": self._counters.questions,
            "answersFetched": self._counters.answers,
            "requestCount": self._counters.requests,
            "bytesReceived": self._counters.bytes_received,
            "lastEventAt": utc_now().isoformat(),
        }
        async with self._session_factory() as session, session.begin():
            job = await update_job_progress(
                session,
                job_id=self._job_id,
                worker_id=self._worker_id,
                progress=progress,
                processed_items=self._counters.questions,
                total_items=max_documents,
                stage=JobStage.PROCESSING,
                checkpoint=checkpoint,
            )
            if job is None:
                raise WorkerJobLost("SOURCE_SYNC job lease потерян")
            await add_job_event(
                session,
                job_id=self._job_id,
                level=JobEventLevel.INFO,
                stage=JobStage.PROCESSING,
                code="CHECKPOINT_SAVED",
                message="Dry-run checkpoint сохранён после завершённого batch",
                metrics={
                    "page": current_page - 1,
                    "questionsFetched": self._counters.questions,
                    "answersFetched": self._counters.answers,
                },
            )

    def _result(self, mode: SourceSyncMode, start_page: int) -> dict[str, object]:
        return {
            "dryRun": True,
            "mode": mode.value,
            "questionsFetched": self._counters.questions,
            "answersFetched": self._counters.answers,
            "requests": self._counters.requests,
            "bytesReceived": self._counters.bytes_received,
            "pages": self._counters.pages,
            "startPage": start_page,
        }


def _checkpoint_int(checkpoint: dict[str, object], key: str, *, default: int = 0) -> int:
    value = checkpoint.get(key)
    return value if type(value) is int and value >= 0 else default
