from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import httpx
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.enums import (
    IngestionResultStatus,
    JobEventLevel,
    JobStage,
    JobStatus,
    SourceSyncMode,
)
from app.db.base import utc_now
from app.db.models.content import Document
from app.db.models.operations import IngestionFailure, Job, Source, SourceSyncState
from app.db.repositories.jobs import add_job_event, update_job_progress
from app.integrations.stackexchange.client import StackExchangeClient
from app.integrations.stackexchange.errors import (
    StackExchangeCancelled,
    StackExchangeClientError,
    StackExchangeQuotaLow,
)
from app.integrations.stackexchange.schemas import (
    StackExchangeAnswer,
    StackExchangeQuestion,
    StackExchangeResponseMetrics,
)
from app.schemas.base import ApiModel
from app.services.document_ingestion import (
    IngestionResult,
    IngestionSkip,
    ingest_question_thread,
)


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
    documents_count: int
    initial_completed: bool
    incremental_watermark: datetime | None
    checkpoint: dict[str, object]
    state_mode: str | None
    state_next_page: int
    state_item_offset: int
    state_fixed_todate: int | None
    initial_request_count: int
    initial_bytes_received: int


@dataclass(slots=True)
class RuntimeCounters:
    questions: int = 0
    answers: int = 0
    requests: int = 0
    bytes_received: int = 0
    pages: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    duplicates: int = 0
    skipped: int = 0
    failed: int = 0
    chunks_created: int = 0


@dataclass(slots=True)
class BatchCounters:
    questions: int = 0
    answers: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    duplicates: int = 0
    skipped: int = 0
    failed: int = 0
    chunks_created: int = 0
    last_activity_at: datetime | None = None
    last_creation_at: datetime | None = None
    warning_codes: Counter[str] = field(default_factory=Counter)


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
        self._counters = RuntimeCounters()
        self._source_documents_count = 0
        self._source_id_value: UUID | None = None

    async def run(self) -> HandlerOutcome:
        try:
            payload, context = await self._load_context()
        except (ValidationError, InvalidSourceSyncPayload):
            return HandlerOutcome(
                "FAILED",
                error_code="INVALID_JOB_PAYLOAD",
                error_message="Payload SOURCE_SYNC не прошёл валидацию",
            )

        mode = self._resolve_mode(payload.mode, context.initial_completed)
        continuation = not payload.dry_run and context.state_mode == mode.value
        checkpoint = context.checkpoint
        self._restore_counters(checkpoint, context)
        start_page = self._start_page(checkpoint, context, continuation)
        item_offset = self._item_offset(checkpoint, context, continuation)
        fixed_todate = self._fixed_todate(checkpoint, context, continuation)
        window_rolled = False
        if mode == SourceSyncMode.INITIAL and start_page > 25 and not self._has_api_key():
            rollover_todate = await self._initial_rollover_todate(context.source_id)
            if rollover_todate is not None:
                fixed_todate = rollover_todate
                start_page = 1
                item_offset = 0
                window_rolled = True
        max_documents = payload.max_documents or (
            200 if payload.dry_run else context.target_documents
        )
        max_pages = payload.max_pages or (
            2 if payload.dry_run else self._settings.stackexchange_max_pages
        )
        fromdate = self._incremental_fromdate(mode, context.incremental_watermark)
        sort = "creation" if mode == SourceSyncMode.INITIAL else "activity"
        traversal_complete = False
        yielded_page = False
        last_has_more = False

        try:
            await self._set_source_syncing(mode, dry_run=payload.dry_run)
            if window_rolled:
                await self._record_page_event(
                    JobStage.FETCHING_QUESTIONS,
                    "INITIAL_WINDOW_ROLLED",
                    "Глубокая пагинация продолжена новым окном todate без API key",
                    {"page": start_page, "todate": fixed_todate},
                )
            if self._initial_target_reached(mode, context.target_documents):
                traversal_complete = True
            elif self._counters.questions < max_documents:
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
                        yielded_page = True
                        if await self._is_cancelled():
                            raise StackExchangeCancelled
                        remaining = self._remaining_documents(
                            mode,
                            max_documents=max_documents,
                            target_documents=context.target_documents,
                        )
                        if remaining <= 0:
                            break
                        offset = item_offset if page.page == start_page else 0
                        available = page.envelope.items[offset:]
                        questions = available[:remaining]
                        if not questions:
                            item_offset = 0
                            last_has_more = page.envelope.has_more
                            continue
                        consumed_page = offset + len(questions) >= len(page.envelope.items)
                        last_has_more = page.envelope.has_more or not consumed_page
                        await self._record_page_event(
                            JobStage.FETCHING_QUESTIONS,
                            "QUESTIONS_PAGE_FETCHED",
                            "Получена страница вопросов Stack Exchange",
                            {
                                "page": page.page,
                                "items": len(questions),
                                "offset": offset,
                            },
                        )
                        await self._set_stage(JobStage.FETCHING_ANSWERS)
                        answers_by_question = await self._fetch_answers(client, questions)
                        batch = await self._process_batch(
                            questions,
                            answers_by_question,
                            dry_run=payload.dry_run,
                            page=page.page,
                        )
                        next_page = page.page + 1 if consumed_page else page.page
                        next_offset = 0 if consumed_page else offset + len(questions)
                        await self._save_checkpoint(
                            mode=mode,
                            dry_run=payload.dry_run,
                            fixed_todate=fixed_todate,
                            next_page=next_page,
                            item_offset=next_offset,
                            last_successful_page=page.page if consumed_page else page.page - 1,
                            max_documents=max_documents,
                            max_pages=max_pages,
                            batch=batch,
                        )
                        item_offset = next_offset
                        traversal_complete = not page.envelope.has_more and consumed_page
                        if (
                            self._remaining_documents(
                                mode,
                                max_documents=max_documents,
                                target_documents=context.target_documents,
                            )
                            <= 0
                        ):
                            break
            if not yielded_page and self._counters.questions < max_documents:
                traversal_complete = True
            elif yielded_page and not last_has_more:
                traversal_complete = True
        except StackExchangeCancelled:
            if await self._has_user_cancellation():
                return HandlerOutcome(
                    "CANCELLED",
                    result=self._result(mode, start_page, fixed_todate, False, payload.dry_run),
                )
            return HandlerOutcome(
                "REQUEUED",
                result=self._result(mode, start_page, fixed_todate, False, payload.dry_run),
                error_code="WORKER_SHUTDOWN",
                error_message="Worker завершает работу после безопасного checkpoint",
                next_attempt_at=utc_now() + timedelta(seconds=5),
            )
        except StackExchangeQuotaLow as exc:
            return HandlerOutcome(
                "REQUEUED",
                result=self._result(mode, start_page, fixed_todate, False, payload.dry_run),
                error_code=exc.code,
                error_message=exc.safe_message,
                next_attempt_at=utc_now() + timedelta(hours=1),
            )
        except StackExchangeClientError as exc:
            if exc.retryable:
                return HandlerOutcome(
                    "REQUEUED",
                    result=self._result(mode, start_page, fixed_todate, False, payload.dry_run),
                    error_code=exc.code,
                    error_message=exc.safe_message,
                    next_attempt_at=utc_now() + timedelta(minutes=5),
                )
            return HandlerOutcome(
                "FAILED",
                result=self._result(mode, start_page, fixed_todate, False, payload.dry_run),
                error_code=exc.code,
                error_message=exc.safe_message,
            )
        except SQLAlchemyError:
            return HandlerOutcome(
                "REQUEUED",
                result=self._result(mode, start_page, fixed_todate, False, payload.dry_run),
                error_code="DATABASE_TEMPORARY_ERROR",
                error_message="PostgreSQL временно не завершил batch ingestion",
                next_attempt_at=utc_now() + timedelta(minutes=1),
            )

        sync_complete = not payload.dry_run and (
            traversal_complete or self._initial_target_reached(mode, context.target_documents)
        )
        return HandlerOutcome(
            "COMPLETED",
            result=self._result(mode, start_page, fixed_todate, sync_complete, payload.dry_run),
        )

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
            state_json = dict(state.state) if state else {}
            return payload, SourceSyncContext(
                source_id=source.id,
                source_page_size=min(source.page_size, self._settings.stackexchange_page_size),
                target_documents=source.target_documents,
                documents_count=source.documents_count,
                initial_completed=bool(state and state.initial_sync_completed_at),
                incremental_watermark=state.incremental_watermark if state else None,
                checkpoint=dict(job.checkpoint),
                state_mode=state.current_mode if state else None,
                state_next_page=state.next_page if state else 1,
                state_item_offset=_checkpoint_int(state_json, "itemOffset"),
                state_fixed_todate=_optional_checkpoint_int(state_json, "fixedTodate"),
                initial_request_count=job.request_count,
                initial_bytes_received=job.bytes_received,
            )

    def _restore_counters(
        self,
        checkpoint: dict[str, object],
        context: SourceSyncContext,
    ) -> None:
        self._counters = RuntimeCounters(
            questions=_checkpoint_int(checkpoint, "questionsFetched"),
            answers=_checkpoint_int(checkpoint, "answersFetched"),
            requests=context.initial_request_count,
            bytes_received=context.initial_bytes_received,
            pages=_checkpoint_int(checkpoint, "pages"),
            inserted=_checkpoint_int(checkpoint, "inserted"),
            updated=_checkpoint_int(checkpoint, "updated"),
            unchanged=_checkpoint_int(checkpoint, "unchanged"),
            duplicates=_checkpoint_int(checkpoint, "duplicates"),
            skipped=_checkpoint_int(checkpoint, "skipped"),
            failed=_checkpoint_int(checkpoint, "failed"),
            chunks_created=_checkpoint_int(checkpoint, "chunksCreated"),
        )
        self._source_documents_count = context.documents_count

    @staticmethod
    def _resolve_mode(requested: SourceSyncMode, initial_completed: bool) -> SourceSyncMode:
        if requested != SourceSyncMode.AUTO:
            return requested
        return SourceSyncMode.INCREMENTAL if initial_completed else SourceSyncMode.INITIAL

    @staticmethod
    def _start_page(
        checkpoint: dict[str, object],
        context: SourceSyncContext,
        continuation: bool,
    ) -> int:
        if "currentPage" in checkpoint:
            return max(1, _checkpoint_int(checkpoint, "currentPage", default=1))
        return max(1, context.state_next_page) if continuation else 1

    @staticmethod
    def _item_offset(
        checkpoint: dict[str, object],
        context: SourceSyncContext,
        continuation: bool,
    ) -> int:
        if "itemOffset" in checkpoint:
            return _checkpoint_int(checkpoint, "itemOffset")
        return context.state_item_offset if continuation else 0

    @staticmethod
    def _fixed_todate(
        checkpoint: dict[str, object],
        context: SourceSyncContext,
        continuation: bool,
    ) -> int:
        stored = _optional_checkpoint_int(checkpoint, "fixedTodate")
        if stored is not None:
            return stored
        if continuation and context.state_fixed_todate is not None:
            return context.state_fixed_todate
        return round(utc_now().timestamp())

    def _incremental_fromdate(
        self,
        mode: SourceSyncMode,
        watermark: datetime | None,
    ) -> int | None:
        if mode != SourceSyncMode.INCREMENTAL or watermark is None:
            return None
        return max(
            0,
            round(watermark.timestamp()) - self._settings.stackexchange_incremental_overlap_seconds,
        )

    def _initial_target_reached(self, mode: SourceSyncMode, target_documents: int) -> bool:
        return mode == SourceSyncMode.INITIAL and self._source_documents_count >= target_documents

    def _has_api_key(self) -> bool:
        key = self._settings.stackexchange_key
        return key is not None and bool(key.get_secret_value())

    async def _initial_rollover_todate(self, source_id: UUID) -> int | None:
        async with self._session_factory() as session:
            oldest = await session.scalar(
                select(func.min(Document.published_at)).where(
                    Document.source_id == source_id,
                    Document.processing_status == "CHUNKED",
                )
            )
        return max(0, round(oldest.timestamp()) - 1) if oldest is not None else None

    def _remaining_documents(
        self,
        mode: SourceSyncMode,
        *,
        max_documents: int,
        target_documents: int,
    ) -> int:
        remaining = max_documents - self._counters.questions
        if mode == SourceSyncMode.INITIAL:
            remaining = min(remaining, target_documents - self._source_documents_count)
        return max(0, remaining)

    async def _fetch_answers(
        self,
        client: StackExchangeClient,
        questions: list[StackExchangeQuestion],
    ) -> dict[int, list[StackExchangeAnswer]]:
        grouped: defaultdict[int, list[StackExchangeAnswer]] = defaultdict(list)
        question_ids = [question.question_id for question in questions]
        if question_ids:
            async for page in client.fetch_answers_for_question_ids(
                question_ids,
                max_pages=self._settings.stackexchange_max_pages,
            ):
                for answer in page.envelope.items:
                    grouped[answer.question_id].append(answer)
        await self._record_page_event(
            JobStage.FETCHING_ANSWERS,
            "ANSWERS_BATCH_FETCHED",
            "Получены страницы ответов для пакета вопросов",
            {
                "questions": len(questions),
                "answers": sum(len(items) for items in grouped.values()),
            },
        )
        return dict(grouped)

    async def _process_batch(
        self,
        questions: list[StackExchangeQuestion],
        answers_by_question: dict[int, list[StackExchangeAnswer]],
        *,
        dry_run: bool,
        page: int,
    ) -> BatchCounters:
        batch = BatchCounters(
            questions=len(questions),
            answers=sum(len(items) for items in answers_by_question.values()),
        )
        for question in questions:
            batch.last_activity_at = _latest_timestamp(
                batch.last_activity_at,
                question.last_activity_date,
            )
            batch.last_creation_at = _latest_timestamp(
                batch.last_creation_at,
                question.creation_date,
            )
        if dry_run:
            self._apply_batch_counters(batch)
            return batch

        await self._set_stage(JobStage.PROCESSING)
        for question in questions:
            if await self._is_cancelled():
                raise StackExchangeCancelled
            try:
                result = await self._ingest_one(
                    question,
                    answers_by_question.get(question.question_id, []),
                )
            except IngestionSkip as exc:
                await self._record_ingestion_skip(question, exc, page=page)
                batch.skipped += 1
                continue
            self._apply_ingestion_result(batch, result)
            batch.warning_codes.update(warning.code for warning in result.warnings)
        self._apply_batch_counters(batch)
        return batch

    async def _ingest_one(
        self,
        question: StackExchangeQuestion,
        answers: list[StackExchangeAnswer],
    ) -> IngestionResult:
        async with self._session_factory() as session, session.begin():
            source = await session.get(Source, self._source_id)
            if source is None:
                raise InvalidSourceSyncPayload
            return await ingest_question_thread(
                session,
                source,
                question,
                answers,
                settings=self._settings,
            )

    @property
    def _source_id(self) -> UUID:
        if self._source_id_value is None:
            raise RuntimeError("SOURCE_SYNC context ещё не загружен")
        return self._source_id_value

    @_source_id.setter
    def _source_id(self, value: UUID) -> None:
        self._source_id_value = value

    @staticmethod
    def _apply_ingestion_result(batch: BatchCounters, result: IngestionResult) -> None:
        if result.status == IngestionResultStatus.INSERTED:
            batch.inserted += 1
        elif result.status == IngestionResultStatus.UPDATED:
            batch.updated += 1
        elif result.status == IngestionResultStatus.UNCHANGED:
            batch.unchanged += 1
        elif result.status == IngestionResultStatus.DUPLICATE:
            batch.duplicates += 1
        batch.chunks_created += result.chunks_created

    def _apply_batch_counters(self, batch: BatchCounters) -> None:
        self._counters.questions += batch.questions
        self._counters.answers += batch.answers
        self._counters.pages += 1
        self._counters.inserted += batch.inserted
        self._counters.updated += batch.updated
        self._counters.unchanged += batch.unchanged
        self._counters.duplicates += batch.duplicates
        self._counters.skipped += batch.skipped
        self._counters.failed += batch.failed
        self._counters.chunks_created += batch.chunks_created

    async def _record_ingestion_skip(
        self,
        question: StackExchangeQuestion,
        error: IngestionSkip,
        *,
        page: int,
    ) -> None:
        async with self._session_factory() as session, session.begin():
            job = await session.get(Job, self._job_id)
            if job is None:
                raise WorkerJobLost("SOURCE_SYNC job отсутствует")
            session.add(
                IngestionFailure(
                    job_id=self._job_id,
                    source_id=self._source_id,
                    external_id=str(question.question_id),
                    entity_type="QUESTION",
                    error_code=error.code[:80],
                    safe_message=error.safe_message[:1000],
                    retryable=False,
                    attempt=job.attempt,
                    context={"page": page},
                )
            )

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

    async def _set_source_syncing(self, mode: SourceSyncMode, *, dry_run: bool) -> None:
        async with self._session_factory() as session, session.begin():
            job = await update_job_progress(
                session,
                job_id=self._job_id,
                worker_id=self._worker_id,
                stage=JobStage.FETCHING_QUESTIONS,
            )
            if job is None or job.source_id is None:
                raise WorkerJobLost("SOURCE_SYNC job lease потерян")
            self._source_id = job.source_id
            source = await session.get(Source, job.source_id, with_for_update=True)
            if source is not None:
                source.status = "SYNCING"
                source.last_error = None
            event_code = (
                "DRY_RUN_SYNC_STARTED"
                if dry_run
                else (
                    "INITIAL_SYNC_STARTED"
                    if mode == SourceSyncMode.INITIAL
                    else "INCREMENTAL_SYNC_STARTED"
                )
            )
            await add_job_event(
                session,
                job_id=self._job_id,
                level=JobEventLevel.INFO,
                stage=JobStage.FETCHING_QUESTIONS,
                code=event_code,
                message=(
                    "Запущена ограниченная проверка Stack Exchange без сохранения документов"
                    if dry_run
                    else "Запущена обработка корпуса Stack Exchange"
                ),
                metrics={"mode": mode.value, "dryRun": dry_run},
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

    async def _save_checkpoint(
        self,
        *,
        mode: SourceSyncMode,
        dry_run: bool,
        fixed_todate: int,
        next_page: int,
        item_offset: int,
        last_successful_page: int,
        max_documents: int,
        max_pages: int,
        batch: BatchCounters,
    ) -> None:
        progress = min(
            99,
            max(
                round(self._counters.questions / max_documents * 100),
                round(self._counters.pages / max_pages * 100),
            ),
        )
        checkpoint: dict[str, object] = {
            "dryRun": dry_run,
            "mode": mode.value,
            "fixedTodate": fixed_todate,
            "currentPage": next_page,
            "itemOffset": item_offset,
            "lastSuccessfulPage": max(0, last_successful_page),
            "questionsFetched": self._counters.questions,
            "answersFetched": self._counters.answers,
            "requestCount": self._counters.requests,
            "bytesReceived": self._counters.bytes_received,
            "pages": self._counters.pages,
            "inserted": self._counters.inserted,
            "updated": self._counters.updated,
            "unchanged": self._counters.unchanged,
            "duplicates": self._counters.duplicates,
            "skipped": self._counters.skipped,
            "failed": self._counters.failed,
            "chunksCreated": self._counters.chunks_created,
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
            if job is None or job.source_id is None:
                raise WorkerJobLost("SOURCE_SYNC job lease потерян")
            if not dry_run:
                state = await session.get(SourceSyncState, job.source_id, with_for_update=True)
                if state is None:
                    state = SourceSyncState(
                        source_id=job.source_id,
                        next_page=1,
                        total_questions_fetched=0,
                        total_answers_fetched=0,
                        total_documents_inserted=0,
                        total_documents_updated=0,
                        total_documents_unchanged=0,
                        total_exact_duplicates=0,
                        total_items_skipped=0,
                        total_errors=0,
                        total_chunks_created=0,
                        state={},
                    )
                    session.add(state)
                state.current_mode = mode
                state.next_page = next_page
                state.last_checkpoint_at = utc_now()
                state.last_job_id = job.id
                if mode == SourceSyncMode.INITIAL and state.initial_snapshot_todate is None:
                    state.initial_snapshot_todate = datetime.fromtimestamp(fixed_todate, UTC)
                state.last_seen_question_activity_at = _latest_datetime(
                    state.last_seen_question_activity_at,
                    batch.last_activity_at,
                )
                state.last_seen_question_creation_at = _latest_datetime(
                    state.last_seen_question_creation_at,
                    batch.last_creation_at,
                )
                state.total_questions_fetched += batch.questions
                state.total_answers_fetched += batch.answers
                state.total_documents_inserted += batch.inserted
                state.total_documents_updated += batch.updated
                state.total_documents_unchanged += batch.unchanged
                state.total_exact_duplicates += batch.duplicates
                state.total_items_skipped += batch.skipped
                state.total_errors += batch.failed
                state.total_chunks_created += batch.chunks_created
                state.state = {
                    "fixedTodate": fixed_todate,
                    "itemOffset": item_offset,
                    "warningCodes": dict(batch.warning_codes),
                }
                source = await session.get(Source, job.source_id, with_for_update=True)
                if source is not None:
                    count = await session.scalar(
                        select(func.count())
                        .select_from(Document)
                        .where(Document.source_id == source.id)
                    )
                    self._source_documents_count = int(count or 0)
                    source.documents_count = self._source_documents_count
                    source.last_sync_at = utc_now()
            await add_job_event(
                session,
                job_id=self._job_id,
                level=JobEventLevel.INFO,
                stage=JobStage.PROCESSING,
                code="CHECKPOINT_SAVED" if dry_run else "BATCH_COMMITTED",
                message=(
                    "Dry-run checkpoint сохранён после завершённого batch"
                    if dry_run
                    else "Batch документов и checkpoint успешно зафиксированы"
                ),
                metrics={
                    "page": next_page,
                    "itemOffset": item_offset,
                    "questionsFetched": self._counters.questions,
                    "answersFetched": self._counters.answers,
                    "inserted": batch.inserted,
                    "updated": batch.updated,
                    "unchanged": batch.unchanged,
                    "duplicates": batch.duplicates,
                    "skipped": batch.skipped,
                    "chunksCreated": batch.chunks_created,
                },
            )

    def _result(
        self,
        mode: SourceSyncMode,
        start_page: int,
        fixed_todate: int,
        sync_complete: bool,
        dry_run: bool,
    ) -> dict[str, object]:
        return {
            "dryRun": dry_run,
            "mode": mode.value,
            "syncComplete": sync_complete,
            "fixedTodate": fixed_todate,
            "questionsFetched": self._counters.questions,
            "answersFetched": self._counters.answers,
            "inserted": self._counters.inserted,
            "updated": self._counters.updated,
            "unchanged": self._counters.unchanged,
            "duplicates": self._counters.duplicates,
            "skipped": self._counters.skipped,
            "failed": self._counters.failed,
            "chunksCreated": self._counters.chunks_created,
            "requests": self._counters.requests,
            "bytesReceived": self._counters.bytes_received,
            "pages": self._counters.pages,
            "startPage": start_page,
            "documentsCount": self._source_documents_count,
        }


def _checkpoint_int(checkpoint: dict[str, object], key: str, *, default: int = 0) -> int:
    value = checkpoint.get(key)
    return value if type(value) is int and value >= 0 else default


def _optional_checkpoint_int(checkpoint: dict[str, object], key: str) -> int | None:
    value = checkpoint.get(key)
    return value if type(value) is int and value >= 0 else None


def _latest_timestamp(current: datetime | None, timestamp: int) -> datetime:
    candidate = datetime.fromtimestamp(timestamp, UTC)
    return max(current, candidate) if current is not None else candidate


def _latest_datetime(current: datetime | None, candidate: datetime | None) -> datetime | None:
    if current is None:
        return candidate
    if candidate is None:
        return current
    return max(current, candidate)
