from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.core.enums import ChunkSectionType, JobEventLevel, JobStage, SourceSyncMode
from app.schemas.base import ApiModel, Pagination


class SourceSyncRequest(ApiModel):
    mode: SourceSyncMode = SourceSyncMode.AUTO
    max_documents: int | None = Field(default=None, ge=1, le=25_000)
    max_pages: int | None = Field(default=None, ge=1, le=250)
    dry_run: bool = False


class SourceSyncStateOut(ApiModel):
    source_id: UUID
    initial_sync_completed_at: datetime | None = None
    initial_snapshot_todate: datetime | None = None
    next_page: int
    incremental_watermark: datetime | None = None
    current_mode: SourceSyncMode | None = None
    last_checkpoint_at: datetime | None = None
    last_seen_question_activity_at: datetime | None = None
    last_seen_question_creation_at: datetime | None = None
    total_questions_fetched: int
    total_answers_fetched: int
    total_documents_inserted: int
    total_documents_updated: int
    total_documents_unchanged: int
    total_exact_duplicates: int
    total_items_skipped: int
    total_errors: int
    total_chunks_created: int
    last_job_id: UUID | None = None
    state: dict[str, object]
    created_at: datetime
    updated_at: datetime


class JobEventOut(ApiModel):
    id: UUID
    job_id: UUID
    level: JobEventLevel
    stage: JobStage
    code: str
    message: str
    metrics: dict[str, object]
    created_at: datetime


class JobEventsResponse(ApiModel):
    items: list[JobEventOut]
    pagination: Pagination


class IngestionStatsOut(ApiModel):
    documents_count: int
    answers_count: int
    chunks_count: int
    revisions_count: int
    failures_count: int
    unresolved_failures_count: int
    processing_statuses: dict[str, int]
    deduplication_statuses: dict[str, int]
    total_questions_fetched: int
    total_answers_fetched: int
    total_documents_inserted: int
    total_documents_updated: int
    total_documents_unchanged: int
    total_exact_duplicates: int
    total_items_skipped: int
    total_errors: int
    total_chunks_created: int


class IngestionFailureOut(ApiModel):
    id: UUID
    job_id: UUID
    source_id: UUID
    document_id: UUID | None = None
    external_id: str | None = None
    entity_type: str
    error_code: str
    safe_message: str
    retryable: bool
    attempt: int
    context: dict[str, object]
    created_at: datetime
    resolved_at: datetime | None = None


class IngestionFailuresResponse(ApiModel):
    items: list[IngestionFailureOut]
    pagination: Pagination


class DocumentChunkOut(ApiModel):
    id: UUID
    chunk_key: str
    document_id: UUID
    document_version: int
    ordinal: int
    section_type: ChunkSectionType
    answer_id: UUID | None = None
    text: str
    contextual_text: str
    content_hash: str
    token_count: int
    character_count: int
    has_code: bool
    language: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentChunksResponse(ApiModel):
    items: list[DocumentChunkOut]
    pagination: Pagination


class DocumentRevisionOut(ApiModel):
    id: UUID
    document_id: UUID
    version: int
    content_hash: str
    metadata_hash: str
    source_updated_at: datetime | None = None
    snapshot: dict[str, object]
    change_reason: str
    created_at: datetime


class DocumentRevisionsResponse(ApiModel):
    items: list[DocumentRevisionOut]
    pagination: Pagination
