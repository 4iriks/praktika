from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.errors import ApiException
from app.core.config import get_settings
from app.core.enums import (
    AuditAction,
    AuditEntityType,
    DeduplicationStatus,
    DocumentStatus,
    JobStatus,
    JobType,
    ProcessingStatus,
    SearchIndexEntryStatus,
    SearchIndexVersionStatus,
    WorkerInstanceStatus,
)
from app.db.base import utc_now
from app.db.models.content import Document, DocumentChunk
from app.db.models.identity import User
from app.db.models.operations import Job, SearchIndexEntry, SearchIndexVersion, WorkerInstance
from app.integrations.embeddings import OllamaEmbeddingProvider
from app.integrations.qdrant import QdrantIndexClient, QdrantIndexError
from app.schemas.base import pagination
from app.schemas.management import BackgroundJobOut
from app.schemas.search_index import (
    CleanupIndexesRequest,
    FullReindexRequest,
    SearchIndexStatsOut,
    SearchIndexVersionOut,
    SearchIndexVersionsResponse,
    ValidateIndexRequest,
)
from app.services.audit import add_audit_event
from app.services.management_serializers import job_to_schema


def version_to_schema(version: SearchIndexVersion) -> SearchIndexVersionOut:
    return SearchIndexVersionOut.model_validate(version)


async def list_index_versions(
    db: AsyncSession, *, status: str, page: int, limit: int
) -> SearchIndexVersionsResponse:
    filters = []
    if status != "ALL":
        try:
            normalized = SearchIndexVersionStatus(status)
        except ValueError as exc:
            raise ApiException(422, "VALIDATION_ERROR", "Неизвестный status индекса") from exc
        filters.append(SearchIndexVersion.status == normalized)
    total = (
        await db.scalar(select(func.count()).select_from(SearchIndexVersion).where(*filters)) or 0
    )
    items = list(
        (
            await db.scalars(
                select(SearchIndexVersion)
                .where(*filters)
                .order_by(SearchIndexVersion.created_at.desc(), SearchIndexVersion.id.desc())
                .offset((page - 1) * limit)
                .limit(limit)
            )
        ).all()
    )
    return SearchIndexVersionsResponse(
        items=[version_to_schema(item) for item in items],
        pagination=pagination(page, limit, total),
    )


async def get_index_version(db: AsyncSession, version_id: UUID) -> SearchIndexVersionOut:
    version = await db.get(SearchIndexVersion, version_id)
    if version is None:
        raise ApiException(404, "NOT_FOUND", "Версия поискового индекса не найдена")
    return version_to_schema(version)


async def get_active_index(db: AsyncSession) -> SearchIndexVersionOut | None:
    version = await db.scalar(
        select(SearchIndexVersion).where(
            SearchIndexVersion.status == SearchIndexVersionStatus.ACTIVE
        )
    )
    return version_to_schema(version) if version is not None else None


async def get_index_stats(db: AsyncSession) -> SearchIndexStatsOut:
    settings = get_settings()
    active = await db.scalar(
        select(SearchIndexVersion).where(
            SearchIndexVersion.status == SearchIndexVersionStatus.ACTIVE
        )
    )
    dedup = [DeduplicationStatus.UNIQUE]
    if settings.index_allow_possible_duplicates:
        dedup.append(DeduplicationStatus.POSSIBLE_DUPLICATE)
    eligible = (
        await db.scalar(
            select(func.count())
            .select_from(DocumentChunk)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                Document.processing_status == ProcessingStatus.CHUNKED,
                Document.status.in_([DocumentStatus.ACTIVE, DocumentStatus.OUTDATED]),
                Document.deduplication_status.in_(dedup),
                Document.processing_error.is_(None),
                DocumentChunk.document_version == Document.version,
                func.length(func.btrim(DocumentChunk.text)) > 0,
            )
        )
        or 0
    )
    indexed = 0
    if active is not None:
        indexed = (
            await db.scalar(
                select(func.count())
                .select_from(SearchIndexEntry)
                .where(
                    SearchIndexEntry.index_version_id == active.id,
                    SearchIndexEntry.status == SearchIndexEntryStatus.INDEXED,
                )
            )
            or 0
        )
    full_job = await db.scalar(
        select(Job)
        .where(
            Job.type == JobType.FULL_REINDEX,
            Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        )
        .options(selectinload(Job.creator))
        .order_by(Job.created_at.desc())
        .limit(1)
    )
    worker = await db.scalar(
        select(WorkerInstance)
        .where(WorkerInstance.capabilities.contains(["search_index"]))
        .order_by(WorkerInstance.heartbeat_at.desc())
        .limit(1)
    )
    indexer_online = bool(
        worker is not None
        and worker.status == WorkerInstanceStatus.RUNNING
        and utc_now() - worker.heartbeat_at
        <= timedelta(seconds=settings.worker_heartbeat_seconds * 2)
    )
    qdrant = QdrantIndexClient(settings)
    embeddings = OllamaEmbeddingProvider(settings)
    try:
        qdrant_health = await qdrant.health()
        embedding_health = await embeddings.health()
        try:
            alias_target = (
                await qdrant.alias_target(settings.qdrant_alias) if qdrant_health.online else None
            )
            points = (
                await qdrant.count(alias_target)
                if qdrant_health.online and alias_target is not None
                else 0
            )
        except QdrantIndexError:
            alias_target = None
            points = 0
    finally:
        await embeddings.close()
        await qdrant.close()
    return SearchIndexStatsOut(
        alias_name=settings.qdrant_alias,
        alias_target=alias_target,
        active_version=version_to_schema(active) if active is not None else None,
        eligible_chunks=eligible,
        indexed_chunks=indexed,
        stale_chunks=max(0, eligible - indexed),
        points_count=points,
        current_full_reindex_job=job_to_schema(full_job) if full_job is not None else None,
        qdrant_online=qdrant_health.online,
        qdrant_version=qdrant_health.version,
        qdrant_message=qdrant_health.message,
        embedding_provider=settings.embedding_provider,
        embedding_model=settings.embedding_model,
        embedding_dimensions=settings.embedding_dimensions,
        embedding_online=embedding_health.online,
        embedding_model_installed=embedding_health.model_installed,
        indexer_online=indexer_online,
        indexer_last_heartbeat_at=worker.heartbeat_at if worker is not None else None,
    )


async def enqueue_full_reindex(
    db: AsyncSession,
    request: Request,
    actor: User,
    payload: FullReindexRequest,
) -> BackgroundJobOut:
    if not payload.confirm:
        raise ApiException(422, "CONFIRMATION_REQUIRED", "Подтвердите полную переиндексацию")
    return await _enqueue_index_job(
        db,
        request,
        actor,
        job_type=JobType.FULL_REINDEX,
        payload={},
        action=AuditAction.START_FULL_REINDEX,
        summary="Создано задание blue-green полной переиндексации",
    )


async def enqueue_validation(
    db: AsyncSession,
    request: Request,
    actor: User,
    version_id: UUID,
    payload: ValidateIndexRequest,
) -> BackgroundJobOut:
    del payload
    if await db.get(SearchIndexVersion, version_id) is None:
        raise ApiException(404, "NOT_FOUND", "Версия поискового индекса не найдена")
    return await _enqueue_index_job(
        db,
        request,
        actor,
        job_type=JobType.SEARCH_INDEX_VALIDATE,
        payload={"indexVersionId": str(version_id)},
        action=AuditAction.VALIDATE_SEARCH_INDEX,
        summary="Создано задание проверки поискового индекса",
    )


async def enqueue_cleanup(
    db: AsyncSession,
    request: Request,
    actor: User,
    payload: CleanupIndexesRequest,
) -> BackgroundJobOut:
    if not payload.dry_run and not payload.confirm:
        raise ApiException(422, "CONFIRMATION_REQUIRED", "Удаление требует confirmation")
    return await _enqueue_index_job(
        db,
        request,
        actor,
        job_type=JobType.SEARCH_INDEX_CLEANUP,
        payload={"dryRun": payload.dry_run, "confirm": payload.confirm},
        action=AuditAction.CLEANUP_SEARCH_INDEX,
        summary="Создано задание очистки производных Qdrant collections",
    )


async def _enqueue_index_job(
    db: AsyncSession,
    request: Request,
    actor: User,
    *,
    job_type: JobType,
    payload: dict[str, object],
    action: AuditAction,
    summary: str,
) -> BackgroundJobOut:
    settings = get_settings()
    job = Job(
        type=job_type,
        status=JobStatus.QUEUED,
        stage="PREPARING",
        progress=0,
        created_by=actor.id,
        cancellable=True,
        payload=payload,
        max_attempts=settings.index_job_max_attempts,
    )
    db.add(job)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise ApiException(409, "CONFLICT", "Такое задание индекса уже выполняется") from exc
    await add_audit_event(
        db,
        request,
        actor=actor,
        action=action,
        entity_type=AuditEntityType.SEARCH_INDEX,
        entity_id=str(job.id),
        entity_label=job.type,
        summary=summary,
        after={"jobId": str(job.id), "type": job.type},
    )
    await db.refresh(job, attribute_names=["creator"])
    return job_to_schema(job)
