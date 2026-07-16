"""Stage 6 search index versions and entries.

Revision ID: 20260716_0004
Revises: 20260716_0003
Create Date: 2026-07-16 18:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260716_0004"
down_revision: str | None = "20260716_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_jobs_job_type_values"), "jobs", type_="check")
    op.create_check_constraint(
        op.f("ck_jobs_job_type_values"),
        "jobs",
        "type IN ('SOURCE_SYNC','DOCUMENT_REPROCESS','DOCUMENT_REINDEX','FULL_REINDEX',"
        "'HEALTH_CHECK','SEARCH_INDEX_VALIDATE','SEARCH_INDEX_CLEANUP')",
    )
    op.create_table(
        "search_index_versions",
        sa.Column("collection_name", sa.String(length=255), nullable=False),
        sa.Column("alias_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("schema_version", sa.String(length=40), nullable=False),
        sa.Column("schema_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding_provider", sa.String(length=40), nullable=False),
        sa.Column("embedding_model", sa.String(length=200), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column("embedding_instruction_hash", sa.String(length=64), nullable=False),
        sa.Column("sparse_provider", sa.String(length=40), nullable=False),
        sa.Column("sparse_model", sa.String(length=200), nullable=False),
        sa.Column("qdrant_server_version", sa.String(length=40), nullable=False),
        sa.Column("qdrant_client_version", sa.String(length=40), nullable=False),
        sa.Column("point_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "eligible_chunk_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("build_job_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("build_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("build_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=80), nullable=True),
        sa.Column("failure_message", sa.String(length=1000), nullable=True),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "status IN ('BUILDING','READY','ACTIVE','FAILED','RETIRED')",
            name=op.f("ck_search_index_versions_search_index_version_status_values"),
        ),
        sa.CheckConstraint(
            "embedding_dimensions > 0",
            name=op.f("ck_search_index_versions_search_index_version_dimensions_positive"),
        ),
        sa.CheckConstraint(
            "point_count >= 0 AND eligible_chunk_count >= 0",
            name=op.f("ck_search_index_versions_search_index_version_counts_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["build_job_id"],
            ["jobs.id"],
            name=op.f("fk_search_index_versions_build_job_id_jobs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_search_index_versions_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_search_index_versions")),
        sa.UniqueConstraint(
            "collection_name", name=op.f("uq_search_index_versions_collection_name")
        ),
    )
    op.create_index(
        op.f("ix_search_index_versions_activated_at"),
        "search_index_versions",
        ["activated_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_search_index_versions_alias_name"),
        "search_index_versions",
        ["alias_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_search_index_versions_build_job_id"),
        "search_index_versions",
        ["build_job_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_search_index_versions_created_at"),
        "search_index_versions",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_search_index_versions_created_by"),
        "search_index_versions",
        ["created_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_search_index_versions_schema_hash"),
        "search_index_versions",
        ["schema_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_search_index_versions_status"),
        "search_index_versions",
        ["status"],
        unique=False,
    )
    op.create_index(
        "uq_search_index_versions_active",
        "search_index_versions",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    op.create_table(
        "search_index_entries",
        sa.Column("index_version_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version", sa.Integer(), nullable=False),
        sa.Column("point_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_content_hash", sa.String(length=64), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("failure_code", sa.String(length=80), nullable=True),
        sa.Column("failure_message", sa.String(length=1000), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "document_version >= 1",
            name=op.f("ck_search_index_entries_search_index_entry_version_positive"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','INDEXED','FAILED','REMOVED')",
            name=op.f("ck_search_index_entries_search_index_entry_status_values"),
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["document_chunks.id"],
            name=op.f("fk_search_index_entries_chunk_id_document_chunks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_search_index_entries_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["index_version_id"],
            ["search_index_versions.id"],
            name=op.f("fk_search_index_entries_index_version_id_search_index_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_search_index_entries")),
        sa.UniqueConstraint(
            "index_version_id",
            "chunk_id",
            name="uq_search_index_entries_index_chunk",
        ),
        sa.UniqueConstraint(
            "index_version_id",
            "point_id",
            name="uq_search_index_entries_index_point",
        ),
    )
    op.create_index(
        op.f("ix_search_index_entries_chunk_id"),
        "search_index_entries",
        ["chunk_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_search_index_entries_document_id"),
        "search_index_entries",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        "ix_search_index_entries_document_version",
        "search_index_entries",
        ["document_id", "document_version"],
        unique=False,
    )
    op.create_index(
        op.f("ix_search_index_entries_index_version_id"),
        "search_index_entries",
        ["index_version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_search_index_entries_indexed_at"),
        "search_index_entries",
        ["indexed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_search_index_entries_point_id"),
        "search_index_entries",
        ["point_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_search_index_entries_status"),
        "search_index_entries",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("search_index_entries")
    op.drop_index("uq_search_index_versions_active", table_name="search_index_versions")
    op.drop_table("search_index_versions")
    op.drop_constraint(op.f("ck_jobs_job_type_values"), "jobs", type_="check")
    op.create_check_constraint(
        op.f("ck_jobs_job_type_values"),
        "jobs",
        "type IN ('SOURCE_SYNC','DOCUMENT_REPROCESS','DOCUMENT_REINDEX',"
        "'FULL_REINDEX','HEALTH_CHECK')",
    )
