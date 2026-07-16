from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.api.errors import ApiException
from app.core.enums import JobEventLevel, JobStage, SourceSyncMode
from app.db.models.content import Answer, Document, DocumentChunk, DocumentRevision
from app.db.models.operations import (
    IngestionFailure,
    Job,
    JobEvent,
    Source,
    SourceSyncState,
)
from app.db.repositories.jobs import sanitize_job_event_metrics
from app.schemas.base import pagination
from app.schemas.ingestion import (
    IngestionFailureOut,
    IngestionFailuresResponse,
    IngestionStatsOut,
    JobEventOut,
    JobEventsResponse,
    SourceSyncStateOut,
)


def job_event_to_schema(event: JobEvent) -> JobEventOut:
    return JobEventOut(
        id=event.id,
        job_id=event.job_id,
        level=JobEventLevel(event.level),
        stage=JobStage(event.stage),
        code=event.code,
        message=event.message,
        metrics=event.metrics,
        created_at=event.created_at,
    )


async def list_job_events(
    db: AsyncSession,
    job_id: UUID,
    *,
    sort: str,
    page: int,
    limit: int,
) -> JobEventsResponse:
    if await db.get(Job, job_id) is None:
        raise ApiException(404, "NOT_FOUND", "Задание не найдено")
    total = (
        await db.scalar(select(func.count()).select_from(JobEvent).where(JobEvent.job_id == job_id))
        or 0
    )
    statement = select(JobEvent).where(JobEvent.job_id == job_id)
    if sort == "created_asc":
        statement = statement.order_by(JobEvent.created_at.asc(), JobEvent.id)
    elif sort == "created_desc":
        statement = statement.order_by(JobEvent.created_at.desc(), JobEvent.id)
    else:
        raise ApiException(422, "VALIDATION_ERROR", "Неизвестная сортировка событий")
    events = (await db.scalars(statement.offset((page - 1) * limit).limit(limit))).all()
    return JobEventsResponse(
        items=[job_event_to_schema(event) for event in events],
        pagination=pagination(page, limit, total),
    )


def source_sync_state_to_schema(state: SourceSyncState) -> SourceSyncStateOut:
    return SourceSyncStateOut(
        source_id=state.source_id,
        initial_sync_completed_at=state.initial_sync_completed_at,
        initial_snapshot_todate=state.initial_snapshot_todate,
        next_page=state.next_page,
        incremental_watermark=state.incremental_watermark,
        current_mode=SourceSyncMode(state.current_mode) if state.current_mode else None,
        last_checkpoint_at=state.last_checkpoint_at,
        last_seen_question_activity_at=state.last_seen_question_activity_at,
        last_seen_question_creation_at=state.last_seen_question_creation_at,
        total_questions_fetched=state.total_questions_fetched,
        total_answers_fetched=state.total_answers_fetched,
        total_documents_inserted=state.total_documents_inserted,
        total_documents_updated=state.total_documents_updated,
        total_documents_unchanged=state.total_documents_unchanged,
        total_exact_duplicates=state.total_exact_duplicates,
        total_items_skipped=state.total_items_skipped,
        total_errors=state.total_errors,
        total_chunks_created=state.total_chunks_created,
        last_job_id=state.last_job_id,
        state=state.state,
        created_at=state.created_at,
        updated_at=state.updated_at,
    )


async def get_or_create_sync_state(db: AsyncSession, source: Source) -> SourceSyncState:
    state = await db.get(SourceSyncState, source.id)
    if state is None:
        state = SourceSyncState(source_id=source.id)
        db.add(state)
        await db.flush()
        await db.refresh(state)
    return state


def ingestion_failure_to_schema(failure: IngestionFailure) -> IngestionFailureOut:
    return IngestionFailureOut(
        id=failure.id,
        job_id=failure.job_id,
        source_id=failure.source_id,
        document_id=failure.document_id,
        external_id=failure.external_id,
        entity_type=failure.entity_type,
        error_code=failure.error_code,
        safe_message=failure.safe_message,
        retryable=failure.retryable,
        attempt=failure.attempt,
        context=sanitize_job_event_metrics(failure.context),
        created_at=failure.created_at,
        resolved_at=failure.resolved_at,
    )


async def get_ingestion_failure(db: AsyncSession, failure_id: UUID) -> IngestionFailureOut:
    failure = await db.get(IngestionFailure, failure_id)
    if failure is None:
        raise ApiException(404, "NOT_FOUND", "Ошибка ingestion не найдена")
    return ingestion_failure_to_schema(failure)


async def list_ingestion_failures(
    db: AsyncSession,
    *,
    source_id: UUID | None,
    job_id: UUID | None,
    external_id: str,
    error_code: str,
    retryable: str,
    resolved: str,
    sort: str,
    page: int,
    limit: int,
) -> IngestionFailuresResponse:
    filters = []
    if source_id is not None:
        filters.append(IngestionFailure.source_id == source_id)
    if job_id is not None:
        filters.append(IngestionFailure.job_id == job_id)
    if external_id.strip():
        filters.append(IngestionFailure.external_id == external_id.strip())
    if error_code.strip():
        filters.append(IngestionFailure.error_code == error_code.strip().upper())
    if retryable in {"true", "false"}:
        filters.append(IngestionFailure.retryable.is_(retryable == "true"))
    elif retryable != "all":
        raise ApiException(422, "VALIDATION_ERROR", "Неизвестный фильтр retryable")
    if resolved in {"true", "false"}:
        filters.append(
            IngestionFailure.resolved_at.is_not(None)
            if resolved == "true"
            else IngestionFailure.resolved_at.is_(None)
        )
    elif resolved != "all":
        raise ApiException(422, "VALIDATION_ERROR", "Неизвестный фильтр resolved")
    total = await db.scalar(select(func.count()).select_from(IngestionFailure).where(*filters)) or 0
    statement = select(IngestionFailure).where(*filters)
    if sort == "created_desc":
        statement = statement.order_by(IngestionFailure.created_at.desc(), IngestionFailure.id)
    elif sort == "created_asc":
        statement = statement.order_by(IngestionFailure.created_at.asc(), IngestionFailure.id)
    else:
        raise ApiException(422, "VALIDATION_ERROR", "Неизвестная сортировка ingestion failures")
    failures = (await db.scalars(statement.offset((page - 1) * limit).limit(limit))).all()
    return IngestionFailuresResponse(
        items=[ingestion_failure_to_schema(failure) for failure in failures],
        pagination=pagination(page, limit, total),
    )


async def ingestion_stats(db: AsyncSession) -> IngestionStatsOut:
    entity_counts = {
        "documents": await _table_count(db, Document),
        "answers": await _table_count(db, Answer),
        "chunks": await _table_count(db, DocumentChunk),
        "revisions": await _table_count(db, DocumentRevision),
        "failures": await _table_count(db, IngestionFailure),
    }
    unresolved = (
        await db.scalar(
            select(func.count())
            .select_from(IngestionFailure)
            .where(IngestionFailure.resolved_at.is_(None))
        )
        or 0
    )
    processing = await _grouped_document_count(db, Document.processing_status)
    deduplication = await _grouped_document_count(db, Document.deduplication_status)
    counter_columns = (
        SourceSyncState.total_questions_fetched,
        SourceSyncState.total_answers_fetched,
        SourceSyncState.total_documents_inserted,
        SourceSyncState.total_documents_updated,
        SourceSyncState.total_documents_unchanged,
        SourceSyncState.total_exact_duplicates,
        SourceSyncState.total_items_skipped,
        SourceSyncState.total_errors,
        SourceSyncState.total_chunks_created,
    )
    totals = (
        await db.execute(
            select(*(func.coalesce(func.sum(column), 0) for column in counter_columns))
        )
    ).one()
    return IngestionStatsOut(
        documents_count=entity_counts["documents"],
        answers_count=entity_counts["answers"],
        chunks_count=entity_counts["chunks"],
        revisions_count=entity_counts["revisions"],
        failures_count=entity_counts["failures"],
        unresolved_failures_count=int(unresolved),
        processing_statuses=processing,
        deduplication_statuses=deduplication,
        total_questions_fetched=int(totals[0]),
        total_answers_fetched=int(totals[1]),
        total_documents_inserted=int(totals[2]),
        total_documents_updated=int(totals[3]),
        total_documents_unchanged=int(totals[4]),
        total_exact_duplicates=int(totals[5]),
        total_items_skipped=int(totals[6]),
        total_errors=int(totals[7]),
        total_chunks_created=int(totals[8]),
    )


async def _table_count(db: AsyncSession, model: type[object]) -> int:
    return int(await db.scalar(select(func.count()).select_from(model)) or 0)


async def _grouped_document_count(
    db: AsyncSession,
    column: InstrumentedAttribute[str],
) -> dict[str, int]:
    rows = (await db.execute(select(column, func.count(Document.id)).group_by(column))).all()
    return {str(status): int(count) for status, count in rows}
