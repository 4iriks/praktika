from __future__ import annotations

import time
from datetime import timedelta

from fastapi import Request
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import (
    AuditAction,
    AuditEntityType,
    JobStatus,
    JobType,
    WorkerInstanceStatus,
)
from app.db.base import utc_now
from app.db.models.content import Answer, Document, DocumentChunk, DocumentRevision
from app.db.models.identity import User
from app.db.models.operations import IngestionFailure, Job, SystemSetting, WorkerInstance
from app.schemas.content import PublicAccessPolicyOut
from app.schemas.management import (
    SystemHardwareOut,
    SystemMetricsOut,
    SystemServiceOut,
    SystemSettingsOut,
    SystemSettingsUpdate,
    SystemStatusOut,
)
from app.services.audit import add_audit_event


async def get_settings_record(db: AsyncSession, *, lock: bool = False) -> SystemSetting:
    statement = select(SystemSetting).where(SystemSetting.singleton_id == 1)
    if lock:
        statement = statement.with_for_update()
    settings = await db.scalar(statement)
    if settings is None:
        settings = SystemSetting(singleton_id=1)
        db.add(settings)
        await db.flush()
    return settings


def settings_to_schema(settings: SystemSetting) -> SystemSettingsOut:
    return SystemSettingsOut(
        search_candidates_limit=settings.search_candidates_limit,
        reranker_limit=settings.reranker_limit,
        rag_sources_limit=settings.rag_sources_limit,
        default_minimum_confidence=settings.default_minimum_confidence,
        allow_guest_search=settings.allow_guest_search,
        allow_guest_rag=settings.allow_guest_rag,
        history_retention_days=settings.history_retention_days,
        audit_retention_days=settings.audit_retention_days,
        updated_at=settings.updated_at,
        updated_by=str(settings.updated_by) if settings.updated_by else None,
    )


async def public_policy(db: AsyncSession) -> PublicAccessPolicyOut:
    settings = await get_settings_record(db)
    return PublicAccessPolicyOut(
        allow_guest_search=settings.allow_guest_search,
        allow_guest_rag=settings.allow_guest_rag,
        rag_sources_limit=settings.rag_sources_limit,
    )


async def update_system_settings(
    db: AsyncSession,
    request: Request,
    actor: User,
    payload: SystemSettingsUpdate,
) -> SystemSettingsOut:
    settings = await get_settings_record(db, lock=True)
    before = settings_to_schema(settings).model_dump(mode="json")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(settings, field, value)
    settings.updated_by = actor.id
    settings.updated_at = utc_now()
    await add_audit_event(
        db,
        request,
        actor=actor,
        action=AuditAction.UPDATE_SYSTEM_SETTINGS,
        entity_type=AuditEntityType.SYSTEM,
        entity_id="system-settings",
        entity_label="Системные настройки",
        summary="Обновлены системные настройки",
        before=before,
        after=settings_to_schema(settings).model_dump(mode="json"),
    )
    await db.flush()
    return settings_to_schema(settings)


async def system_status(db: AsyncSession) -> SystemStatusOut:
    config = get_settings()
    now = utc_now()
    started = time.perf_counter()
    await db.execute(text("SELECT 1"))
    latency = max(1, round((time.perf_counter() - started) * 1000))
    documents = await db.scalar(select(func.count()).select_from(Document)) or 0
    answers = await db.scalar(select(func.count()).select_from(Answer)) or 0
    chunks = await db.scalar(select(func.count()).select_from(DocumentChunk)) or 0
    revisions = await db.scalar(select(func.count()).select_from(DocumentRevision)) or 0
    failures = await db.scalar(select(func.count()).select_from(IngestionFailure)) or 0
    active_jobs = (
        await db.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]))
        )
        or 0
    )
    last_ingestion_at = await db.scalar(
        select(func.max(Job.updated_at)).where(Job.type == JobType.SOURCE_SYNC)
    )
    database_bytes = await db.scalar(select(func.pg_database_size(func.current_database()))) or 0
    services = [
        SystemServiceOut(
            id="frontend",
            name="Frontend",
            status="ONLINE",
            latency_ms=0,
            version=config.app_version,
            last_check_at=now,
            message="Frontend подключается отдельно",
        ),
        SystemServiceOut(
            id="backend",
            name="Backend API",
            status="ONLINE",
            latency_ms=1,
            version=config.app_version,
            last_check_at=now,
            message="FastAPI отвечает",
        ),
        SystemServiceOut(
            id="postgres",
            name="PostgreSQL",
            status="ONLINE",
            latency_ms=latency,
            version="PostgreSQL",
            last_check_at=now,
            message="Соединение установлено",
        ),
    ]
    latest_worker = await db.scalar(
        select(WorkerInstance)
        .where(WorkerInstance.capabilities.contains(["source_sync"]))
        .order_by(WorkerInstance.heartbeat_at.desc(), WorkerInstance.id.desc())
        .limit(1)
    )
    worker_status = "OFFLINE"
    worker_message = "Worker ещё не зарегистрирован"
    worker_last_check = now
    if latest_worker is not None:
        worker_last_check = latest_worker.heartbeat_at
        heartbeat_age = now - latest_worker.heartbeat_at
        online_window = timedelta(seconds=config.worker_heartbeat_seconds * 2)
        degraded_window = timedelta(seconds=config.worker_lease_seconds)
        if latest_worker.status == WorkerInstanceStatus.RUNNING and heartbeat_age <= online_window:
            worker_status = "ONLINE"
            worker_message = "Worker принимает задания SOURCE_SYNC"
        elif (
            latest_worker.status != WorkerInstanceStatus.STOPPED
            and heartbeat_age <= degraded_window
        ):
            worker_status = "DEGRADED"
            worker_message = "Heartbeat worker задерживается или worker завершает работу"
        else:
            worker_message = "Актуальный heartbeat worker отсутствует"
    services.append(
        SystemServiceOut(
            id="crawler",
            name="Crawler worker",
            status=worker_status,
            latency_ms=0,
            version=latest_worker.version if latest_worker is not None else "not running",
            last_check_at=worker_last_check,
            message=worker_message,
        )
    )
    for identifier, name in [
        ("qdrant", "Qdrant"),
        ("ollama", "Ollama"),
        ("indexer", "Indexer"),
        ("bm25", "BM25 index"),
        ("vector", "Vector index"),
        ("embedding", "Embedding model"),
        ("reranker", "Reranker"),
    ]:
        services.append(
            SystemServiceOut(
                id=identifier,
                name=name,
                status="OFFLINE",
                latency_ms=0,
                version="not configured",
                last_check_at=now,
                message="Не настроено на Этапе 5",
            )
        )
    return SystemStatusOut(
        services=services,
        metrics=SystemMetricsOut(
            cpu_usage=0,
            ram_usage_gb=0,
            vram_usage_gb=0,
            disk_usage_gb=0,
            database_size_gb=round(database_bytes / 1024**3, 4),
            vector_index_size_gb=0,
            model_size_gb=0,
            docker_images_estimate_gb=0,
            documents_count=documents,
            answers_count=answers,
            chunks_count=chunks,
            revisions_count=revisions,
            failures_count=failures,
            active_jobs=active_jobs,
            last_ingestion_at=last_ingestion_at,
            application_version=config.app_version,
        ),
        hardware=SystemHardwareOut(
            operating_system="Не определяется из браузера",
            cpu="Не настроено",
            ram_gb=0,
            gpu="Не настроено",
            vram_gb=0,
            project_disk_limit_gb=35,
        ),
        last_check_at=now,
    )


async def run_health_check(db: AsyncSession, request: Request, actor: User) -> SystemStatusOut:
    status = await system_status(db)
    job = Job(
        type=JobType.HEALTH_CHECK,
        status=JobStatus.COMPLETED,
        stage="FINALIZING",
        progress=100,
        processed_items=len(status.services),
        total_items=len(status.services),
        created_by=actor.id,
        cancellable=False,
        created_at=status.last_check_at,
        started_at=status.last_check_at,
        finished_at=status.last_check_at,
    )
    db.add(job)
    await db.flush()
    await add_audit_event(
        db,
        request,
        actor=actor,
        action=AuditAction.HEALTH_CHECK,
        entity_type=AuditEntityType.SYSTEM,
        entity_id=str(job.id),
        entity_label="Проверка сервисов",
        summary="Выполнена проверка состояния сервисов",
        after={"online": sum(item.status == "ONLINE" for item in status.services)},
    )
    return status
