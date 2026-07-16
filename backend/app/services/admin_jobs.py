from __future__ import annotations

from uuid import UUID

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.errors import ApiException
from app.core.config import get_settings
from app.core.enums import AuditAction, AuditEntityType, JobStatus, JobType
from app.db.models.identity import User
from app.db.models.operations import Job, Source
from app.db.repositories.jobs import JobQueueStateError, request_job_cancellation
from app.schemas.management import BackgroundJobOut
from app.services.audit import add_audit_event
from app.services.management_serializers import job_to_schema


async def get_job_record(db: AsyncSession, job_id: UUID, *, lock: bool = False) -> Job:
    statement = select(Job).where(Job.id == job_id).options(selectinload(Job.creator))
    if lock:
        statement = statement.with_for_update()
    job = await db.scalar(statement)
    if job is None:
        raise ApiException(404, "NOT_FOUND", "Задание не найдено")
    return job


async def retry_job(
    db: AsyncSession, request: Request, actor: User, job_id: UUID
) -> BackgroundJobOut:
    original = await get_job_record(db, job_id, lock=True)
    if original.status not in {JobStatus.FAILED, JobStatus.CANCELLED}:
        raise ApiException(
            409, "CONFLICT", "Повторить можно только неудачное или отменённое задание"
        )
    job = Job(
        type=original.type,
        status=JobStatus.QUEUED,
        stage="PREPARING",
        progress=0,
        processed_items=0,
        total_items=original.total_items,
        source_id=original.source_id,
        document_id=original.document_id,
        created_by=actor.id,
        retry_of_job_id=original.id,
        cancellable=True,
        payload=dict(original.payload),
        checkpoint=dict(original.checkpoint),
        max_attempts=get_settings().worker_max_attempts,
        planned_duration_ms=original.planned_duration_ms,
    )
    db.add(job)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise ApiException(409, "CONFLICT", "Активное задание такого типа уже существует") from exc
    if original.source_id:
        source = await db.get(Source, original.source_id)
        if source:
            source.current_job_id = job.id
            source.status = "SYNCING"
    await add_audit_event(
        db,
        request,
        actor=actor,
        action=AuditAction.RETRY_JOB,
        entity_type=AuditEntityType.JOB,
        entity_id=str(job.id),
        entity_label=f"Повтор {original.id}",
        summary="Создан повтор фонового задания",
        after={"retryOfJobId": str(original.id)},
    )
    await db.refresh(job, attribute_names=["creator"])
    return job_to_schema(job)


async def cancel_job(
    db: AsyncSession, request: Request, actor: User, job_id: UUID
) -> BackgroundJobOut:
    job = await get_job_record(db, job_id, lock=True)
    if job.status not in {JobStatus.QUEUED, JobStatus.RUNNING}:
        raise ApiException(409, "CONFLICT", "Это задание нельзя отменить")
    already_requested = job.cancellation_requested_at is not None
    try:
        requested = await request_job_cancellation(db, job_id=job.id)
    except JobQueueStateError as exc:
        raise ApiException(409, "CONFLICT", str(exc)) from exc
    if requested is None:
        raise ApiException(404, "NOT_FOUND", "Задание не найдено")
    if job.source_id:
        source = await db.get(Source, job.source_id)
        if source and source.current_job_id == job.id and job.status == JobStatus.CANCELLED:
            source.current_job_id = None
            source.status = "PAUSED"
        elif source:
            source.last_error = "Запрошена безопасная отмена задания"
    if not already_requested:
        await add_audit_event(
            db,
            request,
            actor=actor,
            action=AuditAction.CANCEL_JOB,
            entity_type=AuditEntityType.JOB,
            entity_id=str(job.id),
            entity_label=job.type,
            summary="Запрошена безопасная отмена фонового задания",
            after={
                "status": job.status,
                "cancellationRequestedAt": job.cancellation_requested_at,
            },
        )
    await db.flush()
    return job_to_schema(job)


async def start_full_reindex(db: AsyncSession, request: Request, actor: User) -> BackgroundJobOut:
    job = Job(
        type=JobType.FULL_REINDEX,
        status=JobStatus.QUEUED,
        stage="PREPARING",
        progress=0,
        created_by=actor.id,
        cancellable=True,
        payload={},
        max_attempts=get_settings().worker_max_attempts,
    )
    db.add(job)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise ApiException(409, "CONFLICT", "Полная переиндексация уже запущена") from exc
    await add_audit_event(
        db,
        request,
        actor=actor,
        action=AuditAction.START_FULL_REINDEX,
        entity_type=AuditEntityType.JOB,
        entity_id=str(job.id),
        entity_label="Полная переиндексация",
        summary="Создано задание полной переиндексации",
    )
    await db.refresh(job, attribute_names=["creator"])
    return job_to_schema(job)
