from __future__ import annotations

import time
from uuid import UUID

import httpx
from fastapi import Request
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiException
from app.core.config import get_settings
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
from app.db.repositories.jobs import JobQueueStateError, request_job_cancellation
from app.integrations.stackexchange.client import StackExchangeClient
from app.integrations.stackexchange.errors import (
    StackExchangeClientError,
    StackExchangeQuotaLow,
)
from app.integrations.stackexchange.schemas import StackExchangeResponseMetrics
from app.schemas.base import pagination
from app.schemas.ingestion import SourceSyncRequest
from app.schemas.management import (
    BackgroundJobOut,
    SourceConnectionResultOut,
    SourceOut,
    SourcesResponse,
    SourceUpdateRequest,
)
from app.services.audit import add_audit_event
from app.services.ingestion import get_or_create_sync_state
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
    source = await get_source_record(db, source_id)
    if source.site != "ru.stackoverflow" or source.base_url != "https://ru.stackoverflow.com":
        raise ApiException(422, "VALIDATION_ERROR", "Источник не входит в разрешённый список")
    await db.commit()
    started = time.perf_counter()
    settings = get_settings()
    last_metrics: StackExchangeResponseMetrics | None = None
    has_more: bool | None = None

    async def capture_metrics(metrics: StackExchangeResponseMetrics) -> None:
        nonlocal last_metrics
        last_metrics = metrics

    success = False
    message = "Stack Exchange API недоступен"
    try:
        async with StackExchangeClient(
            settings,
            client=client,
            on_metrics=capture_metrics,
        ) as stack_client:
            page = await stack_client.fetch_questions_page(
                page=1,
                page_size=min(source.page_size, 5),
                sort="activity",
            )
            has_more = page.envelope.has_more
            success = True
            message = "Подключение установлено"
    except StackExchangeQuotaLow:
        success = True
        message = "Подключение установлено, но квота достигла безопасного резерва"
    except StackExchangeClientError as exc:
        success = False
        message = exc.safe_message
    checked_at = utc_now()
    latency = max(1, round((time.perf_counter() - started) * 1000))
    source = await get_source_record(db, source_id, lock=True)
    source.last_check_at = checked_at
    source.last_error = None if success else message
    if source.enabled:
        source.status = SourceStatus.IDLE if success else SourceStatus.ERROR
    else:
        source.status = SourceStatus.DISABLED
    if last_metrics is not None:
        if last_metrics.quota_remaining is not None:
            source.rate_limit_remaining = last_metrics.quota_remaining
        if last_metrics.quota_max is not None:
            source.rate_limit_total = last_metrics.quota_max
        source.rate_limit_updated_at = checked_at
    source.api_key_configured = settings.stackexchange_key is not None
    await add_audit_event(
        db,
        request,
        actor=actor,
        action=AuditAction.TEST_SOURCE,
        entity_type=AuditEntityType.SOURCE,
        entity_id=str(source.id),
        entity_label=source.name,
        summary="Проверено подключение источника",
        after={
            "success": success,
            "latencyMs": latency,
            "quotaRemaining": last_metrics.quota_remaining if last_metrics else None,
        },
    )
    return SourceConnectionResultOut(
        source_id=source.id,
        success=success,
        latency_ms=latency,
        checked_at=checked_at,
        message=message,
        quota_remaining=last_metrics.quota_remaining if last_metrics else None,
        quota_max=last_metrics.quota_max if last_metrics else None,
        has_more=has_more,
    )


async def start_source_sync(
    db: AsyncSession,
    request: Request,
    actor: User,
    source_id: UUID,
    payload: SourceSyncRequest,
) -> BackgroundJobOut:
    source = await get_source_record(db, source_id, lock=True)
    if not source.enabled or source.status == SourceStatus.DISABLED:
        raise ApiException(409, "CONFLICT", "Отключённый источник нельзя синхронизировать")
    settings = get_settings()
    values = payload.model_dump(mode="json", by_alias=True)
    if payload.dry_run:
        values["maxDocuments"] = payload.max_documents or 200
        values["maxPages"] = payload.max_pages or 2
    job = Job(
        type=JobType.SOURCE_SYNC,
        status=JobStatus.QUEUED,
        stage="PREPARING",
        progress=0,
        total_items=source.target_documents,
        source_id=source.id,
        created_by=actor.id,
        cancellable=True,
        payload={"sourceId": str(source.id), **values},
        max_attempts=settings.worker_max_attempts,
    )
    db.add(job)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise ApiException(409, "CONFLICT", "Синхронизация источника уже запущена") from exc
    source.current_job_id = job.id
    source.status = SourceStatus.SYNCING
    source.last_sync_at = utc_now()
    state = await get_or_create_sync_state(db, source)
    state.last_job_id = job.id
    if not payload.dry_run:
        state.current_mode = payload.mode.value
    state.state = {
        **state.state,
        "lastRequestedMode": payload.mode.value,
        "lastRequestDryRun": payload.dry_run,
    }
    await add_audit_event(
        db,
        request,
        actor=actor,
        action=AuditAction.START_SOURCE_SYNC,
        entity_type=AuditEntityType.SOURCE,
        entity_id=str(source.id),
        entity_label=source.name,
        summary="Создано задание синхронизации источника",
        after={
            "jobId": str(job.id),
            "status": source.status,
            "mode": payload.mode.value,
            "dryRun": payload.dry_run,
        },
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
        job = await db.scalar(
            select(Job)
            .where(
                Job.source_id == source.id,
                Job.type == JobType.SOURCE_SYNC,
                Job.status == JobStatus.CANCELLED,
                Job.cancellation_requested_at.is_not(None),
            )
            .order_by(Job.finished_at.desc(), Job.id)
            .limit(1)
        )
        if job is None:
            raise ApiException(409, "CONFLICT", "Активная синхронизация не найдена")
        await db.refresh(job, attribute_names=["creator"])
        return job_to_schema(job)
    now = utc_now()
    try:
        requested = await request_job_cancellation(db, job_id=job.id, now=now)
    except JobQueueStateError as exc:
        raise ApiException(409, "CONFLICT", str(exc)) from exc
    if requested is None:
        raise ApiException(404, "NOT_FOUND", "Задание не найдено")
    job = requested
    if job.status == JobStatus.CANCELLED:
        source.current_job_id = None
        source.status = SourceStatus.PAUSED
    else:
        source.last_error = "Запрошена безопасная остановка синхронизации"
    await add_audit_event(
        db,
        request,
        actor=actor,
        action=AuditAction.STOP_SOURCE_SYNC,
        entity_type=AuditEntityType.SOURCE,
        entity_id=str(source.id),
        entity_label=source.name,
        summary="Запрошена безопасная остановка синхронизации",
        after={
            "jobId": str(job.id),
            "status": job.status,
            "cancellationRequestedAt": now.isoformat(),
        },
    )
    await db.flush()
    await db.refresh(job, attribute_names=["creator"])
    return job_to_schema(job)
