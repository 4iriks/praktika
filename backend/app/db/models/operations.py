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
    UniqueConstraint,
    and_,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import JobStatus, JobType, SourceStatus, SourceType
from app.db.base import Base, UUIDPrimaryKeyMixin, utc_now

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
    rate_limit_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quota_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
    sync_state: Mapped[SourceSyncState | None] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
        uselist=False,
    )
    ingestion_failures: Mapped[list[IngestionFailure]] = relationship(back_populates="source")

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
    claimed_by: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "worker_instances.id",
            name="fk_jobs_claimed_by_worker_instances",
            ondelete="SET NULL",
            use_alter=True,
        ),
        index=True,
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    cancellation_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    cancellable: Mapped[bool] = mapped_column(Boolean, default=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    checkpoint: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    result: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    bytes_received: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(String(1000))
    planned_duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )

    source: Mapped[Source | None] = relationship(
        back_populates="jobs", foreign_keys=[source_id], lazy="selectin"
    )
    document: Mapped[Document | None] = relationship(back_populates="jobs", lazy="selectin")
    creator: Mapped[User | None] = relationship(foreign_keys=[created_by], lazy="selectin")
    retry_of: Mapped[Job | None] = relationship(remote_side="Job.id")
    claimant: Mapped[WorkerInstance | None] = relationship(
        back_populates="claimed_jobs",
        foreign_keys=[claimed_by],
        lazy="selectin",
    )
    events: Mapped[list[JobEvent]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
    )
    ingestion_failures: Mapped[list[IngestionFailure]] = relationship(back_populates="job")

    __table_args__ = (
        CheckConstraint(
            "type IN ('SOURCE_SYNC','DOCUMENT_REPROCESS','DOCUMENT_REINDEX',"
            "'FULL_REINDEX','HEALTH_CHECK','SEARCH_INDEX_VALIDATE','SEARCH_INDEX_CLEANUP')",
            name="job_type_values",
        ),
        CheckConstraint(
            "status IN ('QUEUED','RUNNING','COMPLETED','FAILED','CANCELLED')",
            name="job_status_values",
        ),
        CheckConstraint(
            "stage IN ('PREPARING','FETCHING_QUESTIONS','FETCHING_ANSWERS',"
            "'WAITING_BACKOFF','PROCESSING','CRAWLING','CLEANING','DEDUPLICATING',"
            "'CHUNKING','EMBEDDING','INDEXING_BM25','INDEXING_VECTOR','FINALIZING')",
            name="job_stage_values",
        ),
        CheckConstraint("progress BETWEEN 0 AND 100", name="job_progress_range"),
        CheckConstraint("attempt >= 0", name="job_attempt_non_negative"),
        CheckConstraint("max_attempts >= 1", name="job_max_attempts_positive"),
        CheckConstraint("attempt <= max_attempts", name="job_attempt_within_limit"),
        CheckConstraint("request_count >= 0", name="job_request_count_non_negative"),
        CheckConstraint("bytes_received >= 0", name="job_bytes_received_non_negative"),
        Index("ix_jobs_claim_queue", "status", "next_attempt_at", "created_at"),
        Index(
            "uq_jobs_active_document_reindex",
            "document_id",
            unique=True,
            postgresql_where=and_(
                type.in_([JobType.DOCUMENT_REINDEX, JobType.DOCUMENT_REPROCESS]),
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


class SourceSyncState(Base):
    __tablename__ = "source_sync_states"

    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
    )
    initial_sync_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    initial_snapshot_todate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_page: Mapped[int] = mapped_column(Integer, default=1)
    incremental_watermark: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_mode: Mapped[str | None] = mapped_column(String(16))
    last_checkpoint_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_question_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_question_creation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_questions_fetched: Mapped[int] = mapped_column(Integer, default=0)
    total_answers_fetched: Mapped[int] = mapped_column(Integer, default=0)
    total_documents_inserted: Mapped[int] = mapped_column(Integer, default=0)
    total_documents_updated: Mapped[int] = mapped_column(Integer, default=0)
    total_documents_unchanged: Mapped[int] = mapped_column(Integer, default=0)
    total_exact_duplicates: Mapped[int] = mapped_column(Integer, default=0)
    total_items_skipped: Mapped[int] = mapped_column(Integer, default=0)
    total_errors: Mapped[int] = mapped_column(Integer, default=0)
    total_chunks_created: Mapped[int] = mapped_column(Integer, default=0)
    last_job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), index=True
    )
    state: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    source: Mapped[Source] = relationship(back_populates="sync_state")
    last_job: Mapped[Job | None] = relationship(foreign_keys=[last_job_id], lazy="selectin")

    __table_args__ = (
        CheckConstraint("next_page >= 1", name="source_sync_state_next_page_positive"),
        CheckConstraint(
            "current_mode IS NULL OR current_mode IN ('AUTO','INITIAL','INCREMENTAL')",
            name="source_sync_state_mode_values",
        ),
        CheckConstraint(
            "total_questions_fetched >= 0 AND total_answers_fetched >= 0 "
            "AND total_documents_inserted >= 0 AND total_documents_updated >= 0 "
            "AND total_documents_unchanged >= 0 AND total_exact_duplicates >= 0 "
            "AND total_items_skipped >= 0 AND total_errors >= 0 "
            "AND total_chunks_created >= 0",
            name="source_sync_state_counters_non_negative",
        ),
    )


class WorkerInstance(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "worker_instances"

    name: Mapped[str] = mapped_column(String(200))
    instance_id: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    capabilities: Mapped[list[str]] = mapped_column(JSONB, default=list)
    version: Mapped[str] = mapped_column(String(80))
    hostname: Mapped[str] = mapped_column(String(255))
    pid: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), index=True)
    current_job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    current_job: Mapped[Job | None] = relationship(
        foreign_keys=[current_job_id],
        lazy="selectin",
        post_update=True,
    )
    claimed_jobs: Mapped[list[Job]] = relationship(
        back_populates="claimant",
        foreign_keys="Job.claimed_by",
    )

    __table_args__ = (
        CheckConstraint("pid > 0", name="worker_instance_pid_positive"),
        CheckConstraint(
            "status IN ('STARTING','RUNNING','STOPPING','STOPPED')",
            name="worker_instance_status_values",
        ),
    )


class JobEvent(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "job_events"

    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    level: Mapped[str] = mapped_column(String(16), index=True)
    stage: Mapped[str] = mapped_column(String(32), index=True)
    code: Mapped[str] = mapped_column(String(80), index=True)
    message: Mapped[str] = mapped_column(String(1000))
    metrics: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    job: Mapped[Job] = relationship(back_populates="events")

    __table_args__ = (
        CheckConstraint(
            "level IN ('DEBUG','INFO','WARNING','ERROR')",
            name="job_event_level_values",
        ),
        CheckConstraint(
            "stage IN ('PREPARING','FETCHING_QUESTIONS','FETCHING_ANSWERS',"
            "'WAITING_BACKOFF','PROCESSING','CRAWLING','CLEANING','DEDUPLICATING',"
            "'CHUNKING','EMBEDDING','INDEXING_BM25','INDEXING_VECTOR','FINALIZING')",
            name="job_event_stage_values",
        ),
        CheckConstraint("length(code) > 0", name="job_event_code_not_empty"),
        CheckConstraint("length(message) > 0", name="job_event_message_not_empty"),
        Index("ix_job_events_job_created_at", "job_id", "created_at"),
    )


class IngestionFailure(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "ingestion_failures"

    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    external_id: Mapped[str | None] = mapped_column(String(120), index=True)
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    error_code: Mapped[str] = mapped_column(String(80), index=True)
    safe_message: Mapped[str] = mapped_column(String(1000))
    retryable: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    context: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    job: Mapped[Job] = relationship(back_populates="ingestion_failures")
    source: Mapped[Source] = relationship(back_populates="ingestion_failures")
    document: Mapped[Document | None] = relationship(back_populates="ingestion_failures")

    __table_args__ = (
        CheckConstraint("length(entity_type) > 0", name="ingestion_failure_entity_not_empty"),
        CheckConstraint("length(error_code) > 0", name="ingestion_failure_code_not_empty"),
        CheckConstraint("length(safe_message) > 0", name="ingestion_failure_message_not_empty"),
        CheckConstraint("attempt >= 0", name="ingestion_failure_attempt_non_negative"),
        CheckConstraint(
            "resolved_at IS NULL OR resolved_at >= created_at",
            name="ingestion_failure_resolution_order",
        ),
        Index("ix_ingestion_failures_source_created_at", "source_id", "created_at"),
        Index("ix_ingestion_failures_job_created_at", "job_id", "created_at"),
    )


class SearchIndexVersion(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "search_index_versions"

    collection_name: Mapped[str] = mapped_column(String(255), unique=True)
    alias_name: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    schema_version: Mapped[str] = mapped_column(String(40))
    schema_hash: Mapped[str] = mapped_column(String(64), index=True)
    embedding_provider: Mapped[str] = mapped_column(String(40))
    embedding_model: Mapped[str] = mapped_column(String(200))
    embedding_dimensions: Mapped[int] = mapped_column(Integer)
    embedding_instruction_hash: Mapped[str] = mapped_column(String(64))
    sparse_provider: Mapped[str] = mapped_column(String(40))
    sparse_model: Mapped[str] = mapped_column(String(200))
    qdrant_server_version: Mapped[str] = mapped_column(String(40))
    qdrant_client_version: Mapped[str] = mapped_column(String(40))
    point_count: Mapped[int] = mapped_column(Integer, default=0)
    eligible_chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    build_job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), index=True
    )
    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    build_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    build_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(80))
    failure_message: Mapped[str | None] = mapped_column(String(1000))
    config: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)

    build_job: Mapped[Job | None] = relationship(foreign_keys=[build_job_id], lazy="selectin")
    creator: Mapped[User | None] = relationship(foreign_keys=[created_by], lazy="selectin")
    entries: Mapped[list[SearchIndexEntry]] = relationship(
        back_populates="index_version", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('BUILDING','READY','ACTIVE','FAILED','RETIRED')",
            name="search_index_version_status_values",
        ),
        CheckConstraint(
            "embedding_dimensions > 0", name="search_index_version_dimensions_positive"
        ),
        CheckConstraint(
            "point_count >= 0 AND eligible_chunk_count >= 0",
            name="search_index_version_counts_non_negative",
        ),
        Index(
            "uq_search_index_versions_active",
            "status",
            unique=True,
            postgresql_where=status == "ACTIVE",
        ),
    )


class SearchIndexEntry(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "search_index_entries"

    index_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("search_index_versions.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    document_version: Mapped[int] = mapped_column(Integer)
    point_id: Mapped[UUID] = mapped_column(index=True)
    chunk_content_hash: Mapped[str] = mapped_column(String(64))
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    failure_code: Mapped[str | None] = mapped_column(String(80))
    failure_message: Mapped[str | None] = mapped_column(String(1000))

    index_version: Mapped[SearchIndexVersion] = relationship(back_populates="entries")

    __table_args__ = (
        UniqueConstraint(
            "index_version_id", "chunk_id", name="uq_search_index_entries_index_chunk"
        ),
        UniqueConstraint(
            "index_version_id", "point_id", name="uq_search_index_entries_index_point"
        ),
        CheckConstraint("document_version >= 1", name="search_index_entry_version_positive"),
        CheckConstraint(
            "status IN ('PENDING','INDEXED','FAILED','REMOVED')",
            name="search_index_entry_status_values",
        ),
        Index(
            "ix_search_index_entries_document_version",
            "document_id",
            "document_version",
        ),
    )


class SearchRun(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "search_runs"

    request_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    query: Mapped[str] = mapped_column(String(1000))
    query_hash: Mapped[str] = mapped_column(String(64), index=True)
    mode: Mapped[str] = mapped_column(String(16), index=True)
    filters: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    requested_limit: Mapped[int] = mapped_column(Integer)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    reranker_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    index_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("search_index_versions.id", ondelete="SET NULL"), index=True
    )
    total_ms: Mapped[int] = mapped_column(Integer, default=0)
    embedding_ms: Mapped[int] = mapped_column(Integer, default=0)
    bm25_ms: Mapped[int] = mapped_column(Integer, default=0)
    vector_ms: Mapped[int] = mapped_column(Integer, default=0)
    fusion_ms: Mapped[int] = mapped_column(Integer, default=0)
    reranker_ms: Mapped[int] = mapped_column(Integer, default=0)
    postgres_hydration_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), index=True)
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    __table_args__ = (
        CheckConstraint("mode IN ('bm25','vector','hybrid')", name="search_run_mode_values"),
        CheckConstraint("status IN ('COMPLETED','FAILED')", name="search_run_status_values"),
        CheckConstraint("requested_limit BETWEEN 1 AND 100", name="search_run_limit_range"),
        CheckConstraint(
            "candidate_count >= 0 AND result_count >= 0",
            name="search_run_counts_non_negative",
        ),
        CheckConstraint(
            "total_ms >= 0 AND embedding_ms >= 0 AND bm25_ms >= 0 "
            "AND vector_ms >= 0 AND fusion_ms >= 0 AND reranker_ms >= 0 "
            "AND postgres_hydration_ms >= 0",
            name="search_run_timings_non_negative",
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
