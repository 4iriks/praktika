from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.base import ApiModel, Pagination
from app.schemas.management import BackgroundJobOut


class SearchIndexVersionOut(ApiModel):
    id: UUID
    collection_name: str
    alias_name: str
    status: str
    schema_version: str
    schema_hash: str
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    sparse_provider: str
    sparse_model: str
    qdrant_server_version: str
    qdrant_client_version: str
    point_count: int
    eligible_chunk_count: int
    build_job_id: UUID | None
    created_at: datetime
    build_started_at: datetime | None
    build_finished_at: datetime | None
    activated_at: datetime | None
    retired_at: datetime | None
    failure_code: str | None
    failure_message: str | None
    config: dict[str, object]


class SearchIndexVersionsResponse(ApiModel):
    items: list[SearchIndexVersionOut]
    pagination: Pagination


class SearchIndexStatsOut(ApiModel):
    alias_name: str
    alias_target: str | None
    active_version: SearchIndexVersionOut | None
    eligible_chunks: int
    indexed_chunks: int
    stale_chunks: int
    points_count: int
    current_full_reindex_job: BackgroundJobOut | None
    qdrant_online: bool
    qdrant_version: str | None
    qdrant_message: str
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    embedding_online: bool
    embedding_model_installed: bool
    indexer_online: bool
    indexer_last_heartbeat_at: datetime | None


class FullReindexRequest(ApiModel):
    confirm: bool


class ValidateIndexRequest(ApiModel):
    confirm: bool = True


class CleanupIndexesRequest(ApiModel):
    dry_run: bool = True
    confirm: bool = False


class SearchIndexJobResponse(ApiModel):
    job: BackgroundJobOut


class IndexCleanupPreviewOut(ApiModel):
    dry_run: bool
    candidates: list[str] = Field(default_factory=list)
