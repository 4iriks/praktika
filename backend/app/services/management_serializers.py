from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    AuditAction,
    AuditEntityType,
    AuditOutcome,
    DocumentStatus,
    IndexStatus,
    JobStage,
    JobStatus,
    JobType,
    SourceStatus,
    SourceType,
    UserRole,
)
from app.db.models.content import Document
from app.db.models.operations import AuditEvent, Job, Source
from app.schemas.management import (
    AuditEventOut,
    BackgroundJobOut,
    ManagedDocumentOut,
    SourceOut,
)
from app.services.content import document_to_schema, selected_tags


def audit_to_schema(event: AuditEvent) -> AuditEventOut:
    return AuditEventOut(
        id=event.id,
        actor_user_id=event.actor_user_id,
        actor_name=event.actor_name,
        actor_role=UserRole(event.actor_role) if event.actor_role else None,
        action=AuditAction(event.action),
        entity_type=AuditEntityType(event.entity_type),
        entity_id=event.entity_id,
        entity_label=event.entity_label,
        outcome=AuditOutcome(event.outcome),
        ip_address=str(event.ip_address or "local"),
        request_id=event.request_id,
        batch_id=event.batch_id,
        created_at=event.created_at,
        summary=event.summary,
        before=event.before,
        after=event.after,
        metadata=event.metadata_json,
        error_code=event.error_code,
    )


def job_to_schema(job: Job) -> BackgroundJobOut:
    duration_ms: int | None = None
    if job.started_at and job.finished_at:
        duration_ms = round((job.finished_at - job.started_at).total_seconds() * 1000)
    creator = job.creator.name if job.creator else "Система"
    return BackgroundJobOut(
        id=job.id,
        type=JobType(job.type),
        status=JobStatus(job.status),
        stage=JobStage(job.stage),
        progress=job.progress,
        processed_items=job.processed_items,
        total_items=job.total_items,
        source_id=job.source_id,
        document_id=job.document_id,
        created_by=creator,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        duration_ms=duration_ms,
        planned_duration_ms=job.planned_duration_ms,
        error_code=job.error_code,
        error_message=job.error_message,
        retry_of_job_id=job.retry_of_job_id,
        cancellable=job.cancellable,
    )


def source_to_schema(source: Source) -> SourceOut:
    return SourceOut(
        id=source.id,
        name=source.name,
        type=SourceType(source.type),
        base_url=source.base_url,
        site=source.site,
        tag=source.tag,
        enabled=source.enabled,
        status=SourceStatus(source.status),
        target_documents=source.target_documents,
        max_additional_answers=source.max_additional_answers,
        page_size=source.page_size,
        documents_count=source.documents_count,
        last_sync_at=source.last_sync_at,
        last_successful_sync_at=source.last_successful_sync_at,
        last_check_at=source.last_check_at,
        rate_limit_remaining=source.rate_limit_remaining,
        rate_limit_total=source.rate_limit_total,
        quota_reset_at=source.quota_reset_at,
        current_job_id=source.current_job_id,
        last_error=source.last_error,
        api_key_configured=source.api_key_configured,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


async def managed_document_to_schema(db: AsyncSession, document: Document) -> ManagedDocumentOut:
    original = await document_to_schema(db, document)
    indexed_at = document.last_indexed_at or document.last_synced_at or datetime.now(UTC)
    return ManagedDocumentOut(
        document_id=document.id,
        status=DocumentStatus(document.status),
        bm25_status=IndexStatus(document.bm25_status),
        vector_status=IndexStatus(document.vector_status),
        chunks_count=document.chunks_count,
        indexed_at=indexed_at,
        last_synced_at=document.last_synced_at,
        content_hash=document.content_hash,
        normalized_title=document.normalized_title,
        managed_tags=[tag.normalized_name for tag in selected_tags(document)],
        editorial_note=document.editorial_note,
        failure_reason=document.failure_reason,
        hidden_reason=document.hidden_reason,
        last_edited_by=document.editor.name if document.editor else None,
        last_edited_at=document.last_edited_at,
        version=document.version,
        source_id=document.source_id,
        original=original,
    )
