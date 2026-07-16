"""Stage 6 hybrid search telemetry and idempotent history.

Revision ID: 20260716_0005
Revises: 20260716_0004
Create Date: 2026-07-16 20:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260716_0005"
down_revision: str | None = "20260716_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("search_history", sa.Column("request_id", sa.String(length=80)))
    op.create_index(
        op.f("ix_search_history_request_id"),
        "search_history",
        ["request_id"],
        unique=True,
    )
    op.create_table(
        "search_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("query", sa.String(length=1000), nullable=False),
        sa.Column("query_hash", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column(
            "filters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("requested_limit", sa.Integer(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reranker_applied", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("index_version_id", sa.Uuid(), nullable=True),
        sa.Column("total_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bm25_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("vector_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fusion_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reranker_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "postgres_hydration_ms", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "mode IN ('bm25','vector','hybrid')",
            name=op.f("ck_search_runs_search_run_mode_values"),
        ),
        sa.CheckConstraint(
            "status IN ('COMPLETED','FAILED')",
            name=op.f("ck_search_runs_search_run_status_values"),
        ),
        sa.CheckConstraint(
            "requested_limit BETWEEN 1 AND 100",
            name=op.f("ck_search_runs_search_run_limit_range"),
        ),
        sa.CheckConstraint(
            "candidate_count >= 0 AND result_count >= 0",
            name=op.f("ck_search_runs_search_run_counts_non_negative"),
        ),
        sa.CheckConstraint(
            "total_ms >= 0 AND embedding_ms >= 0 AND bm25_ms >= 0 "
            "AND vector_ms >= 0 AND fusion_ms >= 0 AND reranker_ms >= 0 "
            "AND postgres_hydration_ms >= 0",
            name=op.f("ck_search_runs_search_run_timings_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_search_runs_user_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["index_version_id"],
            ["search_index_versions.id"],
            name=op.f("fk_search_runs_index_version_id_search_index_versions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_search_runs")),
    )
    for field in (
        "user_id",
        "query_hash",
        "mode",
        "index_version_id",
        "status",
        "created_at",
    ):
        op.create_index(op.f(f"ix_search_runs_{field}"), "search_runs", [field])
    op.create_index(
        op.f("ix_search_runs_request_id"), "search_runs", ["request_id"], unique=True
    )


def downgrade() -> None:
    op.drop_table("search_runs")
    op.drop_index(op.f("ix_search_history_request_id"), table_name="search_history")
    op.drop_column("search_history", "request_id")
