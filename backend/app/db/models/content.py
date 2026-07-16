from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import DocumentStatus, IndexStatus
from app.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.identity import SavedDocument, User
    from app.db.models.operations import Job, Source


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
    )


class Answer(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "answers"

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    external_id: Mapped[str] = mapped_column(String(120))
    author_name: Mapped[str] = mapped_column(String(200))
    body_text: Mapped[str] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)
    score: Mapped[int] = mapped_column(Integer, default=0)
    is_accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    document: Mapped[Document] = relationship(back_populates="answers")

    __table_args__ = (UniqueConstraint("document_id", "external_id"),)


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
