from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    DeduplicationStatus,
    DocumentStatus,
    IndexStatus,
    ProcessingStatus,
)
from app.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.identity import SavedDocument, User
    from app.db.models.operations import IngestionFailure, Job, Source


class Document(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "documents"

    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), index=True
    )
    external_id: Mapped[str] = mapped_column(String(120))
    source_url: Mapped[str] = mapped_column(String(2000))
    original_title: Mapped[str] = mapped_column(String(500))
    normalized_title: Mapped[str] = mapped_column(String(500))
    question_text: Mapped[str] = mapped_column(Text)
    question_html: Mapped[str | None] = mapped_column(Text)
    author_name: Mapped[str] = mapped_column(String(200))
    author_profile_url: Mapped[str | None] = mapped_column(String(2000))
    content_license: Mapped[str | None] = mapped_column(String(120))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score: Mapped[int] = mapped_column(Integer, default=0)
    views_count: Mapped[int] = mapped_column(Integer, default=0)
    answers_count: Mapped[int] = mapped_column(Integer, default=0)
    accepted_answer_external_id: Mapped[str | None] = mapped_column(String(120))
    has_code: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default=DocumentStatus.ACTIVE, index=True)
    bm25_status: Mapped[str] = mapped_column(String(16), default=IndexStatus.NOT_INDEXED)
    vector_status: Mapped[str] = mapped_column(String(16), default=IndexStatus.NOT_INDEXED)
    chunks_count: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[str] = mapped_column(String(128))
    metadata_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    canonical_text: Mapped[str | None] = mapped_column(Text)
    processing_status: Mapped[str] = mapped_column(
        String(16), default=ProcessingStatus.RAW, index=True
    )
    deduplication_status: Mapped[str] = mapped_column(
        String(24), default=DeduplicationStatus.UNIQUE, index=True
    )
    duplicate_of_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    processing_error: Mapped[str | None] = mapped_column(String(1000))
    selected_answers_count: Mapped[int] = mapped_column(Integer, default=0)
    editorial_note: Mapped[str] = mapped_column(String(2000), default="")
    hidden_reason: Mapped[str | None] = mapped_column(String(1000))
    failure_reason: Mapped[str | None] = mapped_column(String(1000))
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_edited_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    last_edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True
    )

    source: Mapped[Source] = relationship(back_populates="documents", lazy="selectin")
    editor: Mapped[User | None] = relationship(foreign_keys=[last_edited_by], lazy="selectin")
    answers: Mapped[list[Answer]] = relationship(
        back_populates="document", cascade="all, delete-orphan", lazy="selectin"
    )
    tag_links: Mapped[list[DocumentTag]] = relationship(
        back_populates="document", cascade="all, delete-orphan", lazy="selectin"
    )
    saved_by: Mapped[list[SavedDocument]] = relationship(back_populates="document")
    jobs: Mapped[list[Job]] = relationship(back_populates="document", lazy="selectin")
    duplicate_of: Mapped[Document | None] = relationship(
        remote_side="Document.id",
        foreign_keys=[duplicate_of_document_id],
        back_populates="exact_duplicates",
        lazy="selectin",
    )
    exact_duplicates: Mapped[list[Document]] = relationship(
        back_populates="duplicate_of",
        foreign_keys="Document.duplicate_of_document_id",
    )
    revisions: Mapped[list[DocumentRevision]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
    ingestion_failures: Mapped[list[IngestionFailure]] = relationship(back_populates="document")

    __table_args__ = (
        UniqueConstraint("source_id", "external_id"),
        CheckConstraint(
            "status IN ('ACTIVE','HIDDEN','PENDING','FAILED','OUTDATED')",
            name="document_status_values",
        ),
        CheckConstraint(
            "bm25_status IN ('READY','PENDING','FAILED','NOT_INDEXED','OUTDATED')",
            name="document_bm25_status_values",
        ),
        CheckConstraint(
            "vector_status IN ('READY','PENDING','FAILED','NOT_INDEXED','OUTDATED')",
            name="document_vector_status_values",
        ),
        CheckConstraint("version >= 1", name="document_version_positive"),
        CheckConstraint(
            "processing_status IN ('RAW','CLEANING','CLEANED','CHUNKING','CHUNKED','FAILED')",
            name="document_processing_status_values",
        ),
        CheckConstraint(
            "deduplication_status IN ('UNIQUE','EXACT_DUPLICATE','POSSIBLE_DUPLICATE')",
            name="document_deduplication_status_values",
        ),
        CheckConstraint(
            "selected_answers_count >= 0",
            name="document_selected_answers_non_negative",
        ),
    )


class Answer(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "answers"

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    external_id: Mapped[str] = mapped_column(String(120))
    author_name: Mapped[str] = mapped_column(String(200))
    author_profile_url: Mapped[str | None] = mapped_column(String(2000))
    body_text: Mapped[str] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)
    sanitized_html: Mapped[str | None] = mapped_column(Text)
    body_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    score: Mapped[int] = mapped_column(Integer, default=0)
    is_accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    selected_for_corpus: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    selection_rank: Mapped[int | None] = mapped_column(Integer)
    source_missing: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    content_license: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    document: Mapped[Document] = relationship(back_populates="answers")
    chunks: Mapped[list[DocumentChunk]] = relationship(back_populates="answer")

    __table_args__ = (
        UniqueConstraint("document_id", "external_id"),
        CheckConstraint(
            "selection_rank IS NULL OR selection_rank >= 1",
            name="answer_selection_rank_positive",
        ),
    )


class Tag(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "tags"

    normalized_name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))

    document_links: Mapped[list[DocumentTag]] = relationship(
        back_populates="tag", cascade="all, delete-orphan"
    )


class DocumentTag(Base):
    __tablename__ = "document_tags"

    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    tag_id: Mapped[UUID] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"))
    is_managed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[Document] = relationship(back_populates="tag_links")
    tag: Mapped[Tag] = relationship(back_populates="document_links", lazy="selectin")

    __table_args__ = (PrimaryKeyConstraint("document_id", "tag_id", "is_managed"),)


class DocumentRevision(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "document_revisions"

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    metadata_hash: Mapped[str] = mapped_column(String(64))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    change_reason: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    document: Mapped[Document] = relationship(back_populates="revisions")

    __table_args__ = (
        UniqueConstraint("document_id", "version"),
        CheckConstraint("version >= 1", name="document_revision_version_positive"),
    )


class DocumentChunk(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "document_chunks"

    chunk_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    document_version: Mapped[int] = mapped_column(Integer)
    ordinal: Mapped[int] = mapped_column(Integer)
    section_type: Mapped[str] = mapped_column(String(24), index=True)
    answer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("answers.id", ondelete="SET NULL"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    contextual_text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    token_count: Mapped[int] = mapped_column(Integer)
    character_count: Mapped[int] = mapped_column(Integer)
    has_code: Mapped[bool] = mapped_column(Boolean, default=False)
    language: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    document: Mapped[Document] = relationship(back_populates="chunks")
    answer: Mapped[Answer | None] = relationship(back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("document_id", "document_version", "ordinal"),
        CheckConstraint("document_version >= 1", name="document_chunk_version_positive"),
        CheckConstraint("ordinal >= 0", name="document_chunk_ordinal_non_negative"),
        CheckConstraint("token_count >= 0", name="document_chunk_token_count_non_negative"),
        CheckConstraint("character_count >= 0", name="document_chunk_character_count_non_negative"),
        CheckConstraint("length(text) > 0", name="document_chunk_text_not_empty"),
        CheckConstraint(
            "section_type IN ('QUESTION','ACCEPTED_ANSWER','ANSWER','MIXED')",
            name="document_chunk_section_type_values",
        ),
        Index("ix_document_chunks_document_version", "document_id", "document_version"),
    )
