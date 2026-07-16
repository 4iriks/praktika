from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

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
from app.schemas.auth import UserOut, UserStatsOut
from app.schemas.base import ApiModel, Pagination
from app.schemas.content import DocumentOut, SearchHistoryOut


class AuditEventOut(ApiModel):
    id: UUID
    actor_user_id: UUID | None = None
    actor_name: str
    actor_role: UserRole | None = None
    action: AuditAction
    entity_type: AuditEntityType
    entity_id: str
    entity_label: str
    outcome: AuditOutcome
    ip_address: str
    request_id: str
    batch_id: str | None = None
    created_at: datetime
    summary: str
    before: dict[str, object] | None = None
    after: dict[str, object] | None = None
    metadata: dict[str, object] | None = None
    error_code: str | None = None


class AuditEventsResponse(ApiModel):
    items: list[AuditEventOut]
    pagination: Pagination


class BackgroundJobOut(ApiModel):
    id: UUID
    type: JobType
    status: JobStatus
    stage: JobStage
    progress: int
    processed_items: int
    total_items: int
    source_id: UUID | None = None
    document_id: UUID | None = None
    created_by: str
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    planned_duration_ms: int
    error_code: str | None = None
    error_message: str | None = None
    retry_of_job_id: UUID | None = None
    cancellable: bool


class JobsResponse(ApiModel):
    items: list[BackgroundJobOut]
    pagination: Pagination


class ManagedDocumentOut(ApiModel):
    document_id: UUID
    status: DocumentStatus
    bm25_status: IndexStatus
    vector_status: IndexStatus
    chunks_count: int
    indexed_at: datetime
    last_synced_at: datetime
    content_hash: str
    normalized_title: str
    managed_tags: list[str]
    editorial_note: str
    failure_reason: str | None = None
    hidden_reason: str | None = None
    last_edited_by: str | None = None
    last_edited_at: datetime | None = None
    version: int
    source_id: UUID
    original: DocumentOut


class ManagedDocumentDetailOut(ManagedDocumentOut):
    audit_events: list[AuditEventOut]
    related_jobs: list[BackgroundJobOut]


class ManagedDocumentsResponse(ApiModel):
    items: list[ManagedDocumentOut]
    available_tags: list[str]
    pagination: Pagination


class ManagedDocumentUpdate(ApiModel):
    normalized_title: str = Field(min_length=1, max_length=500)
    managed_tags: list[str] = Field(min_length=1, max_length=20)
    editorial_note: str = Field(default="", max_length=2000)

    @field_validator("normalized_title", "editorial_note")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("managed_tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        result = list(dict.fromkeys(item.strip().casefold() for item in value if item.strip()))
        if not result:
            raise ValueError("Нужен минимум один тег")
        if any(len(item) > 100 for item in result):
            raise ValueError("Тег не должен быть длиннее 100 символов")
        return result


class HideDocumentRequest(ApiModel):
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


class BulkDocumentRequest(ApiModel):
    document_ids: list[UUID] = Field(min_length=1, max_length=100)
    action: Literal["HIDE", "RESTORE", "REINDEX"]
    reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def require_hide_reason(self) -> BulkDocumentRequest:
        if self.action == "HIDE" and not (self.reason or "").strip():
            raise ValueError("Для скрытия нужна причина")
        return self


class BulkDocumentItemOut(ApiModel):
    document_id: UUID
    outcome: Literal["SUCCESS", "SKIPPED", "FAILED"]
    reason: str | None = None
    job_id: UUID | None = None


class BulkDocumentResultOut(ApiModel):
    batch_id: UUID
    action: Literal["HIDE", "RESTORE", "REINDEX"]
    success_count: int
    skipped_count: int
    failed_count: int
    items: list[BulkDocumentItemOut]


class EditorDashboardOut(ApiModel):
    total_documents: int
    status_counts: dict[DocumentStatus, int]
    bm25_failed: int
    vector_failed: int
    active_jobs: int
    completed_jobs_last_day: int
    attention_documents: list[ManagedDocumentOut]
    recently_edited_documents: list[ManagedDocumentOut]
    recent_jobs: list[BackgroundJobOut]
    recent_failed_jobs: list[BackgroundJobOut]


class AdminUserOut(UserOut):
    stats: UserStatsOut


class AdminUsersResponse(ApiModel):
    items: list[AdminUserOut]
    pagination: Pagination


class AdminUserDetailOut(AdminUserOut):
    recent_history: list[SearchHistoryOut]
    recent_audit_events: list[AuditEventOut]


class ChangeRoleRequest(ApiModel):
    role: UserRole


class BlockUserRequest(ApiModel):
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


class SourceOut(ApiModel):
    id: UUID
    name: str
    type: SourceType
    base_url: str
    site: str
    tag: str
    enabled: bool
    status: SourceStatus
    target_documents: int
    max_additional_answers: int
    page_size: int
    documents_count: int
    last_sync_at: datetime | None = None
    last_successful_sync_at: datetime | None = None
    last_check_at: datetime | None = None
    rate_limit_remaining: int
    rate_limit_total: int
    quota_reset_at: datetime
    current_job_id: UUID | None = None
    last_error: str | None = None
    api_key_configured: bool
    created_at: datetime
    updated_at: datetime


class SourcesResponse(ApiModel):
    items: list[SourceOut]
    pagination: Pagination


class SourceUpdateRequest(ApiModel):
    target_documents: int | None = Field(default=None, ge=5000, le=100000)
    max_additional_answers: int | None = Field(default=None, ge=0, le=3)
    page_size: int | None = Field(default=None, ge=1, le=100)
    enabled: bool | None = None


class SourceConnectionResultOut(ApiModel):
    source_id: UUID
    success: bool
    latency_ms: int
    checked_at: datetime
    message: str


class SystemServiceOut(ApiModel):
    id: str
    name: str
    status: Literal["ONLINE", "DEGRADED", "OFFLINE", "STARTING"]
    latency_ms: int
    version: str
    last_check_at: datetime
    message: str


class SystemMetricsOut(ApiModel):
    cpu_usage: float
    ram_usage_gb: float
    vram_usage_gb: float
    disk_usage_gb: float
    database_size_gb: float
    vector_index_size_gb: float
    model_size_gb: float
    docker_images_estimate_gb: float
    documents_count: int
    chunks_count: int
    application_version: str


class SystemHardwareOut(ApiModel):
    operating_system: str
    cpu: str
    ram_gb: int
    gpu: str
    vram_gb: int
    project_disk_limit_gb: int


class SystemStatusOut(ApiModel):
    services: list[SystemServiceOut]
    metrics: SystemMetricsOut
    hardware: SystemHardwareOut
    last_check_at: datetime


class SystemSettingsOut(ApiModel):
    search_candidates_limit: int
    reranker_limit: int
    rag_sources_limit: int
    default_minimum_confidence: float
    allow_guest_search: bool
    allow_guest_rag: bool
    history_retention_days: int
    audit_retention_days: int
    updated_at: datetime
    updated_by: str | None = None


class SystemSettingsUpdate(ApiModel):
    search_candidates_limit: int | None = Field(default=None, ge=10, le=1000)
    reranker_limit: int | None = Field(default=None, ge=1, le=100)
    rag_sources_limit: int | None = Field(default=None, ge=1, le=20)
    default_minimum_confidence: float | None = Field(default=None, ge=0, le=1)
    allow_guest_search: bool | None = None
    allow_guest_rag: bool | None = None
    history_retention_days: int | None = Field(default=None, ge=1, le=3650)
    audit_retention_days: int | None = Field(default=None, ge=30, le=3650)


class DashboardTimeSeriesOut(ApiModel):
    date: str
    searches: int
    rag_requests: int


class DashboardTagMetricOut(ApiModel):
    tag: str
    count: int


class DashboardStatusMetricOut(ApiModel):
    status: DocumentStatus
    count: int


class AdminDashboardOut(ApiModel):
    total_users: int
    active_users: int
    blocked_users: int
    users_by_role: dict[UserRole, int]
    documents_count: int
    chunks_count: int
    searches_last_day: int
    rag_last_day: int
    average_search_ms: float
    average_rag_ms: float
    job_success_rate: float
    index_size_gb: float
    last_sync_at: datetime | None = None
    query_series: list[DashboardTimeSeriesOut]
    document_statuses: list[DashboardStatusMetricOut]
    popular_tags: list[DashboardTagMetricOut]
