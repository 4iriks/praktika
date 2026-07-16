from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    and_,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import JobStatus, JobType, SourceStatus, SourceType
from app.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.content import Document
    from app.db.models.identity import Role, User


class PermissionRecord(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    roles: Mapped[list[Role]] = relationship(
        secondary="role_permissions", back_populates="permissions"
    )


class Source(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "sources"

    name: Mapped[str] = mapped_column(String(200), unique=True)
    type: Mapped[str] = mapped_column(String(40), default=SourceType.STACK_EXCHANGE)
    base_url: Mapped[str] = mapped_column(String(2000))
    site: Mapped[str] = mapped_column(String(120))
    tag: Mapped[str] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(16), default=SourceStatus.IDLE, index=True)
    target_documents: Mapped[int] = mapped_column(Integer, default=25000)
    max_additional_answers: Mapped[int] = mapped_column(Integer, default=3)
    page_size: Mapped[int] = mapped_column(Integer, default=100)
    documents_count: Mapped[int] = mapped_column(Integer, default=0)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rate_limit_remaining: Mapped[int] = mapped_column(Integer, default=300)
    rate_limit_total: Mapped[int] = mapped_column(Integer, default=300)
    quota_reset_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    current_job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "jobs.id",
            name="fk_sources_current_job_id_jobs",
            ondelete="SET NULL",
            use_alter=True,
        ),
        index=True,
    )
    last_error: Mapped[str | None] = mapped_column(String(1000))
    api_key_configured: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    documents: Mapped[list[Document]] = relationship(back_populates="source")
    jobs: Mapped[list[Job]] = relationship(back_populates="source", foreign_keys="Job.source_id")

    __table_args__ = (
        CheckConstraint("type IN ('STACK_EXCHANGE')", name="source_type_values"),
        CheckConstraint(
            "status IN ('IDLE','CHECKING','SYNCING','PAUSED','ERROR','DISABLED')",
            name="source_status_values",
        ),
        CheckConstraint("target_documents BETWEEN 5000 AND 100000", name="source_target_range"),
        CheckConstraint("max_additional_answers BETWEEN 0 AND 3", name="source_answers_range"),
        CheckConstraint("page_size BETWEEN 1 AND 100", name="source_page_size_range"),
    )


class Job(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "jobs"

    type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), default=JobStatus.QUEUED, index=True)
    stage: Mapped[str] = mapped_column(String(32), default="PREPARING", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    processed_items: Mapped[int] = mapped_column(Integer, default=0)
    total_items: Mapped[int] = mapped_column(Integer, default=0)
    source_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), index=True
    )
    document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    retry_of_job_id: Mapped[UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    cancellable: Mapped[bool] = mapped_column(Boolean, default=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(String(1000))
    planned_duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    source: Mapped[Source | None] = relationship(
        back_populates="jobs", foreign_keys=[source_id], lazy="selectin"
    )
    document: Mapped[Document | None] = relationship(back_populates="jobs", lazy="selectin")
    creator: Mapped[User | None] = relationship(foreign_keys=[created_by], lazy="selectin")
    retry_of: Mapped[Job | None] = relationship(remote_side="Job.id")

    __table_args__ = (
        CheckConstraint(
            "type IN ('SOURCE_SYNC','DOCUMENT_REINDEX','FULL_REINDEX','HEALTH_CHECK')",
            name="job_type_values",
        ),
        CheckConstraint(
            "status IN ('QUEUED','RUNNING','COMPLETED','FAILED','CANCELLED')",
            name="job_status_values",
        ),
        CheckConstraint(
            "stage IN ('PREPARING','CRAWLING','CLEANING','DEDUPLICATING','CHUNKING',"
            "'EMBEDDING','INDEXING_BM25','INDEXING_VECTOR','FINALIZING')",
            name="job_stage_values",
        ),
        CheckConstraint("progress BETWEEN 0 AND 100", name="job_progress_range"),
        Index(
            "uq_jobs_active_document_reindex",
            "document_id",
            unique=True,
            postgresql_where=and_(
                type == JobType.DOCUMENT_REINDEX,
                status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            ),
        ),
        Index(
            "uq_jobs_active_source_sync",
            "source_id",
            unique=True,
            postgresql_where=and_(
                type == JobType.SOURCE_SYNC,
                status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            ),
        ),
        Index(
            "uq_jobs_active_full_reindex",
            "type",
            unique=True,
            postgresql_where=and_(
                type == JobType.FULL_REINDEX,
                status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            ),
        ),
    )


class AuditEvent(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "audit_events"

    actor_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    actor_name: Mapped[str] = mapped_column(String(200))
    actor_role: Mapped[str | None] = mapped_column(String(16), index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[str] = mapped_column(String(120), index=True)
    entity_label: Mapped[str] = mapped_column(String(500))
    outcome: Mapped[str] = mapped_column(String(16), index=True)
    ip_address: Mapped[str | None] = mapped_column(INET)
    request_id: Mapped[str] = mapped_column(String(80), index=True)
    batch_id: Mapped[str | None] = mapped_column(String(80), index=True)
    summary: Mapped[str] = mapped_column(String(1000))
    before: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column("metadata", JSONB)
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    actor: Mapped[User | None] = relationship(back_populates="audit_events", lazy="selectin")

    __table_args__ = (
        CheckConstraint("outcome IN ('SUCCESS','FAILURE')", name="audit_outcome_values"),
    )


class SystemSetting(Base):
    __tablename__ = "system_settings"

    singleton_id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    search_candidates_limit: Mapped[int] = mapped_column(Integer, default=100)
    reranker_limit: Mapped[int] = mapped_column(Integer, default=20)
    rag_sources_limit: Mapped[int] = mapped_column(Integer, default=5)
    default_minimum_confidence: Mapped[float] = mapped_column(Float, default=0.55)
    allow_guest_search: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_guest_rag: Mapped[bool] = mapped_column(Boolean, default=True)
    history_retention_days: Mapped[int] = mapped_column(Integer, default=365)
    audit_retention_days: Mapped[int] = mapped_column(Integer, default=730)
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("singleton_id = 1", name="system_settings_singleton"),
        CheckConstraint(
            "search_candidates_limit BETWEEN 10 AND 1000", name="settings_candidates_range"
        ),
        CheckConstraint("reranker_limit BETWEEN 1 AND 100", name="settings_reranker_range"),
        CheckConstraint("rag_sources_limit BETWEEN 1 AND 20", name="settings_rag_sources_range"),
        CheckConstraint(
            "default_minimum_confidence BETWEEN 0 AND 1", name="settings_confidence_range"
        ),
        CheckConstraint(
            "history_retention_days BETWEEN 1 AND 3650", name="settings_history_retention_range"
        ),
        CheckConstraint(
            "audit_retention_days BETWEEN 30 AND 3650", name="settings_audit_retention_range"
        ),
    )
