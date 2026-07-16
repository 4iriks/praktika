from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiException
from app.core.enums import JobEventLevel, JobStage, SourceSyncMode
from app.db.models.operations import Job, JobEvent, Source, SourceSyncState
from app.schemas.base import pagination
from app.schemas.ingestion import JobEventOut, JobEventsResponse, SourceSyncStateOut


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
        total_questions_fetched=state.total_questions_fetched,
        total_answers_fetched=state.total_answers_fetched,
        total_documents_inserted=state.total_documents_inserted,
        total_documents_updated=state.total_documents_updated,
        total_documents_unchanged=state.total_documents_unchanged,
        total_exact_duplicates=state.total_exact_duplicates,
        total_items_skipped=state.total_items_skipped,
        total_errors=state.total_errors,
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
