from __future__ import annotations

import time
from uuid import UUID

import httpx
from fastapi import Request
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiException
from app.core.enums import (
    AuditAction,
    AuditEntityType,
    JobStatus,
    JobType,
    SourceStatus,
)
from app.db.base import utc_now
from app.db.models.identity import User
from app.db.models.operations import Job, Source
from app.schemas.base import pagination
from app.schemas.management import (
    BackgroundJobOut,
    SourceConnectionResultOut,
    SourceOut,
    SourcesResponse,
    SourceUpdateRequest,
)
from app.services.audit import add_audit_event
from app.services.management_serializers import job_to_schema, source_to_schema


async def get_source_record(db: AsyncSession, source_id: UUID, *, lock: bool = False) -> Source:
    statement = select(Source).where(Source.id == source_id)
    if lock:
        statement = statement.with_for_update()
    source = await db.scalar(statement)
    if source is None:
        raise ApiException(404, "NOT_FOUND", "Источник не найден")
    return source


async def list_sources(
    db: AsyncSession,
    *,
    q: str,
    status: str,
    enabled: str,
    page: int,
    limit: int,
) -> SourcesResponse:
    filters = []
    if q:
        filters.append(or_(Source.name.ilike(f"%{q}%"), Source.site.ilike(f"%{q}%")))
    if status != "ALL":
        filters.append(Source.status == status)
    if enabled != "all":
        filters.append(Source.enabled.is_(enabled == "true"))
    total = await db.scalar(select(func.count()).select_from(Source).where(*filters)) or 0
    items = (
        await db.scalars(
            select(Source)
            .where(*filters)
            .order_by(Source.name, Source.id)
            .offset((page - 1) * limit)
            .limit(limit)
        )
    ).all()
    return SourcesResponse(
        items=[source_to_schema(item) for item in items],
        pagination=pagination(page, limit, total),
    )


async def update_source(
    db: AsyncSession,
    request: Request,
    actor: User,
    source_id: UUID,
    payload: SourceUpdateRequest,
) -> SourceOut:
    source = await get_source_record(db, source_id, lock=True)
    before = source_to_schema(source).model_dump(mode="json")
    changes = payload.model_dump(exclude_none=True)
    for field, value in changes.items():
        setattr(source, field, value)
    if payload.enabled is False:
        active = await db.scalar(
            select(Job).where(
                Job.source_id == source.id,
                Job.type == JobType.SOURCE_SYNC,
                Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            )
        )
        if active:
            raise ApiException(409, "CONFLICT", "Нельзя отключить источник во время синхронизации")
        source.status = SourceStatus.DISABLED
    elif payload.enabled is True and source.status == SourceStatus.DISABLED:
        source.status = SourceStatus.IDLE
    await add_audit_event(
        db,
        request,
        actor=actor,
        action=AuditAction.UPDATE_SOURCE,
        entity_type=AuditEntityType.SOURCE,
        entity_id=str(source.id),
        entity_label=source.name,
        summary="Обновлена конфигурация источника",
        before=before,
        after=source_to_schema(source).model_dump(mode="json"),
    )
    await db.flush()
    await db.refresh(source)
    return source_to_schema(source)


async def test_source_connection(
    db: AsyncSession,
    request: Request,
    actor: User,
    source_id: UUID,
    client: httpx.AsyncClient | None = None,
) -> SourceConnectionResultOut:
    source = await get_source_record(db, source_id, lock=True)
    if source.site != "ru.stackoverflow" or source.base_url != "https://ru.stackoverflow.com":
        raise ApiException(422, "VALIDATION_ERROR", "Источник не входит в разрешённый список")
    started = time.perf_counter()
    own_client = client is None
    value = client or httpx.AsyncClient(timeout=httpx.Timeout(5.0))
    success = False
    message = "Stack Exchange API недоступен"
    try:
        response = await value.get(
            "https://api.stackexchange.com/2.3/info",
            params={"site": source.site},
        )
        success = response.is_success
        message = "Подключение установлено" if success else "API вернул безопасную ошибку"
    except httpx.HTTPError:
        success = False
    finally:
        if own_client:
            await value.aclose()
    checked_at = utc_now()
    latency = max(1, round((time.perf_counter() - started) * 1000))
    source.last_check_at = checked_at
    source.last_error = None if success else message
    source.status = SourceStatus.IDLE if success and source.enabled else SourceStatus.ERROR
    await add_audit_event(
        db,
        request,
        actor=actor,
        action=AuditAction.TEST_SOURCE,
        entity_type=AuditEntityType.SOURCE,
        entity_id=str(source.id),
        entity_label=source.name,
        summary="Проверено подключение источника",
        after={"success": success, "latencyMs": latency},
    )
    return SourceConnectionResultOut(
        source_id=source.id,
        success=success,
        latency_ms=latency,
        checked_at=checked_at,
        message=message,
    )


async def start_source_sync(
    db: AsyncSession, request: Request, actor: User, source_id: UUID
) -> BackgroundJobOut:
    source = await get_source_record(db, source_id, lock=True)
    if not source.enabled or source.status == SourceStatus.DISABLED:
        raise ApiException(409, "CONFLICT", "Отключённый источник нельзя синхронизировать")
    job = Job(
        type=JobType.SOURCE_SYNC,
        status=JobStatus.QUEUED,
        stage="PREPARING",
        progress=0,
        total_items=source.target_documents,
        source_id=source.id,
        created_by=actor.id,
        cancellable=True,
        payload={"sourceId": str(source.id)},
    )
    db.add(job)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise ApiException(409, "CONFLICT", "Синхронизация источника уже запущена") from exc
    source.current_job_id = job.id
    source.status = SourceStatus.SYNCING
    source.last_sync_at = utc_now()
    await add_audit_event(
        db,
        request,
        actor=actor,
        action=AuditAction.START_SOURCE_SYNC,
        entity_type=AuditEntityType.SOURCE,
        entity_id=str(source.id),
        entity_label=source.name,
        summary="Создано задание синхронизации источника",
        after={"jobId": str(job.id), "status": source.status},
    )
    await db.refresh(job, attribute_names=["creator"])
    return job_to_schema(job)


async def stop_source_sync(
    db: AsyncSession, request: Request, actor: User, source_id: UUID
) -> BackgroundJobOut:
    source = await get_source_record(db, source_id, lock=True)
    job = await db.scalar(
        select(Job)
        .where(
            Job.source_id == source.id,
            Job.type == JobType.SOURCE_SYNC,
            Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        )
        .with_for_update()
    )
    if job is None:
        raise ApiException(409, "CONFLICT", "Активная синхронизация не найдена")
    job.status = JobStatus.CANCELLED
    job.finished_at = utc_now()
    job.cancellable = False
    source.current_job_id = None
    source.status = SourceStatus.PAUSED
    await add_audit_event(
        db,
        request,
        actor=actor,
        action=AuditAction.STOP_SOURCE_SYNC,
        entity_type=AuditEntityType.SOURCE,
        entity_id=str(source.id),
        entity_label=source.name,
        summary="Синхронизация источника остановлена",
        after={"jobId": str(job.id), "status": job.status},
    )
    await db.flush()
    await db.refresh(job, attribute_names=["creator"])
    return job_to_schema(job)
