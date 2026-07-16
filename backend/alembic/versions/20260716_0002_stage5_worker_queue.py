"""Add the Stage 5 durable worker queue infrastructure.

Revision ID: 20260716_0002
Revises: 20260715_0001
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260716_0002"
down_revision: str | None = "20260715_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ACTIVE_STATUSES_SQL = "('QUEUED', 'RUNNING')"
JOB_TYPES_SQL = (
    "('SOURCE_SYNC','DOCUMENT_REPROCESS','DOCUMENT_REINDEX','FULL_REINDEX','HEALTH_CHECK')"
)
JOB_STAGES_SQL = (
    "('PREPARING','FETCHING_QUESTIONS','FETCHING_ANSWERS','WAITING_BACKOFF',"
    "'PROCESSING','CRAWLING','CLEANING','DEDUPLICATING','CHUNKING','EMBEDDING',"
    "'INDEXING_BM25','INDEXING_VECTOR','FINALIZING')"
)


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column("rate_limit_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column(
        "sources",
        "quota_reset_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
        server_default=None,
    )
    op.execute("UPDATE sources SET quota_reset_at = NULL")

    op.drop_index("uq_jobs_active_source_sync", table_name="jobs")
    op.drop_index("uq_jobs_active_full_reindex", table_name="jobs")
    op.drop_index("uq_jobs_active_document_reindex", table_name="jobs")
    op.drop_constraint(op.f("ck_jobs_job_type_values"), "jobs", type_="check")
    op.drop_constraint(op.f("ck_jobs_job_stage_values"), "jobs", type_="check")

    op.add_column("jobs", sa.Column("claimed_by", sa.Uuid(), nullable=True))
    op.add_column("jobs", sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "jobs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("jobs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "jobs", sa.Column("attempt", sa.Integer(), server_default=sa.text("0"), nullable=False)
    )
    op.add_column(
        "jobs",
        sa.Column("max_attempts", sa.Integer(), server_default=sa.text("5"), nullable=False),
    )
    op.add_column(
        "jobs", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "jobs",
        sa.Column("cancellation_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "checkpoint",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "jobs",
        sa.Column("request_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "jobs",
        sa.Column("bytes_received", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )

    op.create_check_constraint(
        op.f("ck_jobs_job_type_values"), "jobs", f"type IN {JOB_TYPES_SQL}"
    )
    op.create_check_constraint(
        op.f("ck_jobs_job_stage_values"), "jobs", f"stage IN {JOB_STAGES_SQL}"
    )
    op.create_check_constraint(
        op.f("ck_jobs_job_attempt_non_negative"), "jobs", "attempt >= 0"
    )
    op.create_check_constraint(
        op.f("ck_jobs_job_max_attempts_positive"), "jobs", "max_attempts >= 1"
    )
    op.create_check_constraint(
        op.f("ck_jobs_job_attempt_within_limit"), "jobs", "attempt <= max_attempts"
    )
    op.create_check_constraint(
        op.f("ck_jobs_job_request_count_non_negative"), "jobs", "request_count >= 0"
    )
    op.create_check_constraint(
        op.f("ck_jobs_job_bytes_received_non_negative"), "jobs", "bytes_received >= 0"
    )

    op.create_index(op.f("ix_jobs_claimed_by"), "jobs", ["claimed_by"], unique=False)
    op.create_index(
        op.f("ix_jobs_lease_expires_at"), "jobs", ["lease_expires_at"], unique=False
    )
    op.create_index(
        op.f("ix_jobs_next_attempt_at"), "jobs", ["next_attempt_at"], unique=False
    )
    op.create_index(
        op.f("ix_jobs_cancellation_requested_at"),
        "jobs",
        ["cancellation_requested_at"],
        unique=False,
    )
    op.create_index(
        "ix_jobs_claim_queue",
        "jobs",
        ["status", "next_attempt_at", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_jobs_active_source_sync",
        "jobs",
        ["source_id"],
        unique=True,
        postgresql_where=sa.text(
            f"type = 'SOURCE_SYNC' AND status IN {ACTIVE_STATUSES_SQL}"
        ),
    )
    op.create_index(
        "uq_jobs_active_document_reindex",
        "jobs",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text(
            "type IN ('DOCUMENT_REINDEX', 'DOCUMENT_REPROCESS') "
            f"AND status IN {ACTIVE_STATUSES_SQL}"
        ),
    )
    op.create_index(
        "uq_jobs_active_full_reindex",
        "jobs",
        ["type"],
        unique=True,
        postgresql_where=sa.text(
            f"type = 'FULL_REINDEX' AND status IN {ACTIVE_STATUSES_SQL}"
        ),
    )

    op.create_table(
        "worker_instances",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("instance_id", sa.String(length=200), nullable=False),
        sa.Column(
            "capabilities",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("version", sa.String(length=80), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("pid", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("current_job_id", sa.Uuid(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "heartbeat_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "pid > 0", name=op.f("ck_worker_instances_worker_instance_pid_positive")
        ),
        sa.CheckConstraint(
            "status IN ('STARTING','RUNNING','STOPPING','STOPPED')",
            name=op.f("ck_worker_instances_worker_instance_status_values"),
        ),
        sa.ForeignKeyConstraint(
            ["current_job_id"],
            ["jobs.id"],
            name=op.f("fk_worker_instances_current_job_id_jobs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_worker_instances")),
    )
    op.create_index(
        op.f("ix_worker_instances_instance_id"),
        "worker_instances",
        ["instance_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_worker_instances_status"), "worker_instances", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_worker_instances_current_job_id"),
        "worker_instances",
        ["current_job_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_worker_instances_heartbeat_at"),
        "worker_instances",
        ["heartbeat_at"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_jobs_claimed_by_worker_instances",
        "jobs",
        "worker_instances",
        ["claimed_by"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "source_sync_states",
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("initial_sync_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("initial_snapshot_todate", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_page", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("incremental_watermark", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_mode", sa.String(length=16), nullable=True),
        sa.Column("last_checkpoint_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_seen_question_activity_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "total_questions_fetched",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "total_answers_fetched",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "total_documents_inserted",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "total_documents_updated",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "total_documents_unchanged",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "total_exact_duplicates",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "total_items_skipped",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "total_errors", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("last_job_id", sa.Uuid(), nullable=True),
        sa.Column(
            "state",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "next_page >= 1",
            name=op.f("ck_source_sync_states_source_sync_state_next_page_positive"),
        ),
        sa.CheckConstraint(
            "current_mode IS NULL OR current_mode IN ('AUTO','INITIAL','INCREMENTAL')",
            name=op.f("ck_source_sync_states_source_sync_state_mode_values"),
        ),
        sa.CheckConstraint(
            "total_questions_fetched >= 0 AND total_answers_fetched >= 0 "
            "AND total_documents_inserted >= 0 AND total_documents_updated >= 0 "
            "AND total_documents_unchanged >= 0 AND total_exact_duplicates >= 0 "
            "AND total_items_skipped >= 0 AND total_errors >= 0",
            name=op.f("ck_source_sync_states_source_sync_state_counters_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["last_job_id"],
            ["jobs.id"],
            name=op.f("fk_source_sync_states_last_job_id_jobs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_source_sync_states_source_id_sources"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("source_id", name=op.f("pk_source_sync_states")),
    )
    op.create_index(
        op.f("ix_source_sync_states_last_job_id"),
        "source_sync_states",
        ["last_job_id"],
        unique=False,
    )

    op.create_table(
        "job_events",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("message", sa.String(length=1000), nullable=False),
        sa.Column(
            "metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "level IN ('DEBUG','INFO','WARNING','ERROR')",
            name=op.f("ck_job_events_job_event_level_values"),
        ),
        sa.CheckConstraint(
            f"stage IN {JOB_STAGES_SQL}",
            name=op.f("ck_job_events_job_event_stage_values"),
        ),
        sa.CheckConstraint(
            "length(code) > 0", name=op.f("ck_job_events_job_event_code_not_empty")
        ),
        sa.CheckConstraint(
            "length(message) > 0", name=op.f("ck_job_events_job_event_message_not_empty")
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_job_events_job_id_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_events")),
    )
    op.create_index(op.f("ix_job_events_job_id"), "job_events", ["job_id"], unique=False)
    op.create_index(op.f("ix_job_events_level"), "job_events", ["level"], unique=False)
    op.create_index(op.f("ix_job_events_stage"), "job_events", ["stage"], unique=False)
    op.create_index(op.f("ix_job_events_code"), "job_events", ["code"], unique=False)
    op.create_index(
        op.f("ix_job_events_created_at"), "job_events", ["created_at"], unique=False
    )
    op.create_index(
        "ix_job_events_job_created_at",
        "job_events",
        ["job_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "ingestion_failures",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=120), nullable=True),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=False),
        sa.Column("safe_message", sa.String(length=1000), nullable=False),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("attempt", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "context",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "length(entity_type) > 0",
            name=op.f("ck_ingestion_failures_ingestion_failure_entity_not_empty"),
        ),
        sa.CheckConstraint(
            "length(error_code) > 0",
            name=op.f("ck_ingestion_failures_ingestion_failure_code_not_empty"),
        ),
        sa.CheckConstraint(
            "length(safe_message) > 0",
            name=op.f("ck_ingestion_failures_ingestion_failure_message_not_empty"),
        ),
        sa.CheckConstraint(
            "attempt >= 0",
            name=op.f("ck_ingestion_failures_ingestion_failure_attempt_non_negative"),
        ),
        sa.CheckConstraint(
            "resolved_at IS NULL OR resolved_at >= created_at",
            name=op.f("ck_ingestion_failures_ingestion_failure_resolution_order"),
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_ingestion_failures_job_id_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_ingestion_failures_source_id_sources"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingestion_failures")),
    )
    op.create_index(
        op.f("ix_ingestion_failures_job_id"),
        "ingestion_failures",
        ["job_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ingestion_failures_source_id"),
        "ingestion_failures",
        ["source_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ingestion_failures_external_id"),
        "ingestion_failures",
        ["external_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ingestion_failures_entity_type"),
        "ingestion_failures",
        ["entity_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ingestion_failures_error_code"),
        "ingestion_failures",
        ["error_code"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ingestion_failures_retryable"),
        "ingestion_failures",
        ["retryable"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ingestion_failures_created_at"),
        "ingestion_failures",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ingestion_failures_resolved_at"),
        "ingestion_failures",
        ["resolved_at"],
        unique=False,
    )
    op.create_index(
        "ix_ingestion_failures_source_created_at",
        "ingestion_failures",
        ["source_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ingestion_failures_job_created_at",
        "ingestion_failures",
        ["job_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_constraint("fk_jobs_claimed_by_worker_instances", "jobs", type_="foreignkey")

    op.drop_table("ingestion_failures")
    op.drop_table("job_events")
    op.drop_table("source_sync_states")
    op.drop_table("worker_instances")

    op.drop_index("uq_jobs_active_source_sync", table_name="jobs")
    op.drop_index("uq_jobs_active_full_reindex", table_name="jobs")
    op.drop_index("uq_jobs_active_document_reindex", table_name="jobs")
    op.drop_index("ix_jobs_claim_queue", table_name="jobs")
    op.drop_index(op.f("ix_jobs_cancellation_requested_at"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_next_attempt_at"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_lease_expires_at"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_claimed_by"), table_name="jobs")

    op.drop_constraint(op.f("ck_jobs_job_bytes_received_non_negative"), "jobs", type_="check")
    op.drop_constraint(op.f("ck_jobs_job_request_count_non_negative"), "jobs", type_="check")
    op.drop_constraint(op.f("ck_jobs_job_attempt_within_limit"), "jobs", type_="check")
    op.drop_constraint(op.f("ck_jobs_job_max_attempts_positive"), "jobs", type_="check")
    op.drop_constraint(op.f("ck_jobs_job_attempt_non_negative"), "jobs", type_="check")
    op.drop_constraint(op.f("ck_jobs_job_stage_values"), "jobs", type_="check")
    op.drop_constraint(op.f("ck_jobs_job_type_values"), "jobs", type_="check")

    op.drop_column("jobs", "bytes_received")
    op.drop_column("jobs", "request_count")
    op.drop_column("jobs", "result")
    op.drop_column("jobs", "checkpoint")
    op.drop_column("jobs", "cancellation_requested_at")
    op.drop_column("jobs", "next_attempt_at")
    op.drop_column("jobs", "max_attempts")
    op.drop_column("jobs", "attempt")
    op.drop_column("jobs", "heartbeat_at")
    op.drop_column("jobs", "lease_expires_at")
    op.drop_column("jobs", "claimed_at")
    op.drop_column("jobs", "claimed_by")

    op.create_check_constraint(
        op.f("ck_jobs_job_type_values"),
        "jobs",
        "type IN ('SOURCE_SYNC','DOCUMENT_REINDEX','FULL_REINDEX','HEALTH_CHECK')",
    )
    op.create_check_constraint(
        op.f("ck_jobs_job_stage_values"),
        "jobs",
        "stage IN ('PREPARING','CRAWLING','CLEANING','DEDUPLICATING','CHUNKING',"
        "'EMBEDDING','INDEXING_BM25','INDEXING_VECTOR','FINALIZING')",
    )
    op.create_index(
        "uq_jobs_active_source_sync",
        "jobs",
        ["source_id"],
        unique=True,
        postgresql_where=sa.text(
            f"type = 'SOURCE_SYNC' AND status IN {ACTIVE_STATUSES_SQL}"
        ),
    )
    op.create_index(
        "uq_jobs_active_document_reindex",
        "jobs",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text(
            f"type = 'DOCUMENT_REINDEX' AND status IN {ACTIVE_STATUSES_SQL}"
        ),
    )
    op.create_index(
        "uq_jobs_active_full_reindex",
        "jobs",
        ["type"],
        unique=True,
        postgresql_where=sa.text(
            f"type = 'FULL_REINDEX' AND status IN {ACTIVE_STATUSES_SQL}"
        ),
    )
    op.execute("UPDATE sources SET quota_reset_at = now() WHERE quota_reset_at IS NULL")
    op.alter_column(
        "sources",
        "quota_reset_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )
    op.drop_column("sources", "rate_limit_updated_at")
