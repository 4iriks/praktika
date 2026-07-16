"""Stage 6 local RAG responses, citations and history links.

Revision ID: 20260716_0006
Revises: 20260716_0005
Create Date: 2026-07-16 21:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260716_0006"
down_revision: str | None = "20260716_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rag_responses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("query", sa.String(length=1000), nullable=False),
        sa.Column("search_mode", sa.String(length=16), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("model_version", sa.String(length=200), nullable=True),
        sa.Column("prompt_version", sa.String(length=40), nullable=False),
        sa.Column("prompt_hash", sa.String(length=64), nullable=False),
        sa.Column("index_version_id", sa.Uuid(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("confidence_label", sa.String(length=16), nullable=False),
        sa.Column("insufficient_context", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "citation_validation_passed", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("search_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reranker_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("generation_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "search_mode IN ('bm25','vector','hybrid')",
            name=op.f("ck_rag_responses_rag_response_search_mode_values"),
        ),
        sa.CheckConstraint(
            "status IN ('GENERATING','COMPLETED','FAILED','CANCELLED')",
            name=op.f("ck_rag_responses_rag_response_status_values"),
        ),
        sa.CheckConstraint(
            "confidence_label IN ('LOW','MEDIUM','HIGH')",
            name=op.f("ck_rag_responses_rag_response_confidence_label_values"),
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 0 AND 1",
            name=op.f("ck_rag_responses_rag_response_confidence_range"),
        ),
        sa.CheckConstraint(
            "source_count >= 0",
            name=op.f("ck_rag_responses_rag_response_source_count_non_negative"),
        ),
        sa.CheckConstraint(
            "search_ms >= 0 AND reranker_ms >= 0 AND generation_ms >= 0 AND total_ms >= 0",
            name=op.f("ck_rag_responses_rag_response_timings_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["index_version_id"],
            ["search_index_versions.id"],
            name=op.f("fk_rag_responses_index_version_id_search_index_versions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_rag_responses_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rag_responses")),
    )
    for field in (
        "request_id",
        "user_id",
        "search_mode",
        "prompt_hash",
        "index_version_id",
        "insufficient_context",
        "status",
        "created_at",
    ):
        op.create_index(
            op.f(f"ix_rag_responses_{field}"),
            "rag_responses",
            [field],
            unique=field == "request_id",
        )

    op.create_table(
        "rag_response_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("response_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("citation_index", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("bm25_score", sa.Float(), nullable=True),
        sa.Column("vector_score", sa.Float(), nullable=True),
        sa.Column("fusion_score", sa.Float(), nullable=False),
        sa.Column("reranker_score", sa.Float(), nullable=True),
        sa.Column("source_url", sa.String(length=2000), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("passage_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "citation_index >= 1", name=op.f("ck_rag_response_sources_rag_source_citation_positive")
        ),
        sa.CheckConstraint(
            "rank >= 1", name=op.f("ck_rag_response_sources_rag_source_rank_positive")
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["document_chunks.id"],
            name=op.f("fk_rag_response_sources_chunk_id_document_chunks"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_rag_response_sources_document_id_documents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["response_id"],
            ["rag_responses.id"],
            name=op.f("fk_rag_response_sources_response_id_rag_responses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rag_response_sources")),
        sa.UniqueConstraint(
            "response_id", "citation_index", name="uq_rag_sources_response_citation"
        ),
        sa.UniqueConstraint("response_id", "chunk_id", name="uq_rag_sources_response_chunk"),
    )
    for field in ("response_id", "chunk_id", "document_id"):
        op.create_index(op.f(f"ix_rag_response_sources_{field}"), "rag_response_sources", [field])

    op.add_column("search_history", sa.Column("response_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_search_history_response_id_rag_responses"),
        "search_history",
        "rag_responses",
        ["response_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_search_history_response_id"), "search_history", ["response_id"])
    op.add_column("feedback", sa.Column("rag_response_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_feedback_rag_response_id_rag_responses"),
        "feedback",
        "rag_responses",
        ["rag_response_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(op.f("ix_feedback_rag_response_id"), "feedback", ["rag_response_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_feedback_rag_response_id"), table_name="feedback")
    op.drop_constraint(
        op.f("fk_feedback_rag_response_id_rag_responses"), "feedback", type_="foreignkey"
    )
    op.drop_column("feedback", "rag_response_id")
    op.drop_index(op.f("ix_search_history_response_id"), table_name="search_history")
    op.drop_constraint(
        op.f("fk_search_history_response_id_rag_responses"),
        "search_history",
        type_="foreignkey",
    )
    op.drop_column("search_history", "response_id")
    op.drop_table("rag_response_sources")
    op.drop_table("rag_responses")
