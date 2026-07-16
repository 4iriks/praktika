from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.core.enums import JobEventLevel, JobStage, SourceSyncMode
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
    total_questions_fetched: int
    total_answers_fetched: int
    total_documents_inserted: int
    total_documents_updated: int
    total_documents_unchanged: int
    total_exact_duplicates: int
    total_items_skipped: int
    total_errors: int
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
