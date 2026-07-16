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
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import AccountStatus, SearchMode, SearchView
from app.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.content import Document
    from app.db.models.operations import AuditEvent, PermissionRecord


class Role(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    users: Mapped[list[User]] = relationship(back_populates="role")
    permissions: Mapped[list[PermissionRecord]] = relationship(
        secondary="role_permissions", back_populates="roles", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint("code IN ('USER','EDITOR','ADMIN')", name="role_code_values"),
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    permission_id: Mapped[UUID] = mapped_column(ForeignKey("permissions.id", ondelete="CASCADE"))

    __table_args__ = (PrimaryKeyConstraint("role_id", "permission_id"),)


class User(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "users"

    role_id: Mapped[UUID] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(320))
    normalized_email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default=AccountStatus.ACTIVE, index=True)
    account_version: Mapped[int] = mapped_column(Integer, default=1)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    blocked_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    block_reason: Mapped[str | None] = mapped_column(String(500))

    role: Mapped[Role] = relationship(back_populates="users", lazy="selectin")
    preferences: Mapped[UserPreference] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )
    sessions: Mapped[list[Session]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    history: Mapped[list[SearchHistory]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    saved_documents: Mapped[list[SavedDocument]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    feedback: Mapped[list[Feedback]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    audit_events: Mapped[list[AuditEvent]] = relationship(back_populates="actor")

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','BLOCKED')", name="user_status_values"),
        CheckConstraint("account_version >= 1", name="user_account_version_positive"),
    )


class Session(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "sessions"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64))
    account_version: Mapped[int] = mapped_column(Integer)
    remember_me: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(500))

    user: Mapped[User] = relationship(back_populates="sessions", lazy="selectin")


class UserPreference(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    default_search_mode: Mapped[str] = mapped_column(String(16), default=SearchMode.HYBRID)
    default_search_view: Mapped[str] = mapped_column(String(16), default=SearchView.DOCUMENTS)
    default_page_size: Mapped[int] = mapped_column(Integer, default=10)
    auto_expand_scores: Mapped[bool] = mapped_column(Boolean, default=False)
    confirm_external_links: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="preferences")

    __table_args__ = (
        CheckConstraint(
            "default_search_mode IN ('bm25','vector','hybrid')",
            name="preference_search_mode_values",
        ),
        CheckConstraint(
            "default_search_view IN ('documents','answer')",
            name="preference_search_view_values",
        ),
        CheckConstraint("default_page_size IN (10,20,50)", name="preference_page_size_values"),
    )


class SearchHistory(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "search_history"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    request_id: Mapped[str | None] = mapped_column(String(80), unique=True, index=True)
    query: Mapped[str] = mapped_column(String(1000))
    view: Mapped[str] = mapped_column(String(16))
    mode: Mapped[str] = mapped_column(String(16))
    filters: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    sort: Mapped[str] = mapped_column(String(32), default="relevance")
    page_size: Mapped[int] = mapped_column(Integer, default=10)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    took_ms: Mapped[int] = mapped_column(Integer, default=0)
    answer_preview: Mapped[str | None] = mapped_column(String(1000))
    insufficient_context: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    user: Mapped[User] = relationship(back_populates="history")

    __table_args__ = (
        CheckConstraint("view IN ('documents','answer')", name="history_view_values"),
        CheckConstraint("mode IN ('bm25','vector','hybrid')", name="history_mode_values"),
    )


class SavedDocument(Base):
    __tablename__ = "saved_documents"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="saved_documents")
    document: Mapped[Document] = relationship(back_populates="saved_by", lazy="selectin")

    __table_args__ = (PrimaryKeyConstraint("user_id", "document_id"),)


class Feedback(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "feedback"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    response_id: Mapped[str] = mapped_column(String(120))
    value: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(String(40))
    question: Mapped[str] = mapped_column(String(1000))
    comment: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="feedback")

    __table_args__ = (
        UniqueConstraint("user_id", "response_id"),
        CheckConstraint("value IN ('positive','negative')", name="feedback_value_values"),
    )
