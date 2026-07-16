from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.api.errors import ApiException
from app.core.enums import AccountStatus, AuditAction, AuditEntityType, SearchView, UserRole
from app.db.base import utc_now
from app.db.models.identity import Feedback, Role, SavedDocument, SearchHistory, User
from app.db.models.operations import AuditEvent
from app.db.repositories.sessions import revoke_user_sessions
from app.db.repositories.users import get_role, get_user_by_id, user_statement
from app.schemas.auth import UserStatsOut
from app.schemas.base import pagination
from app.schemas.management import (
    AdminUserDetailOut,
    AdminUserOut,
    AdminUsersResponse,
)
from app.services.audit import add_audit_event
from app.services.management_serializers import audit_to_schema
from app.services.serializers import user_to_schema
from app.services.user import history_schema

LAST_ADMIN_LOCK_ID = 7_904_113_001


def stats_subqueries() -> tuple[
    ColumnElement[int],
    ColumnElement[int],
    ColumnElement[int],
    ColumnElement[int],
]:
    history = (
        select(func.count())
        .select_from(SearchHistory)
        .where(SearchHistory.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )
    document_searches = (
        select(func.count())
        .select_from(SearchHistory)
        .where(
            SearchHistory.user_id == User.id,
            SearchHistory.view == SearchView.DOCUMENTS,
        )
        .correlate(User)
        .scalar_subquery()
    )
    rag = history - document_searches
    saved = (
        select(func.count())
        .select_from(SavedDocument)
        .where(SavedDocument.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )
    feedback = (
        select(func.count())
        .select_from(Feedback)
        .where(Feedback.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )
    return document_searches, rag, saved, feedback


def admin_user_schema(
    user: User,
    document_searches: int,
    rag_searches: int,
    saved_documents: int,
    rated_answers: int,
) -> AdminUserOut:
    return AdminUserOut(
        **user_to_schema(user).model_dump(),
        stats=UserStatsOut(
            document_searches=document_searches,
            rag_searches=rag_searches,
            saved_documents=saved_documents,
            rated_answers=rated_answers,
        ),
    )


async def list_admin_users(
    db: AsyncSession,
    *,
    q: str,
    role: str,
    status: str,
    registered_from: datetime | None,
    registered_to: datetime | None,
    sort: str,
    page: int,
    limit: int,
) -> AdminUsersResponse:
    filters = []
    if q:
        filters.append(or_(User.name.ilike(f"%{q}%"), User.email.ilike(f"%{q}%")))
    if role != "ALL":
        filters.append(Role.code == role)
    if status != "ALL":
        filters.append(User.status == status)
    if registered_from:
        filters.append(User.registered_at >= registered_from)
    if registered_to:
        filters.append(User.registered_at <= registered_to)
    count_statement = select(func.count()).select_from(User).join(Role).where(*filters)
    total = await db.scalar(count_statement) or 0
    stats = stats_subqueries()
    statement = user_statement().add_columns(*stats).join(Role).where(*filters)
    if sort == "created_desc":
        statement = statement.order_by(User.registered_at.desc(), User.id)
    elif sort == "created_asc":
        statement = statement.order_by(User.registered_at.asc(), User.id)
    elif sort == "activity_desc":
        statement = statement.order_by(User.last_active_at.desc(), User.id)
    elif sort == "name_asc":
        statement = statement.order_by(User.name.asc(), User.id)
    else:
        raise ApiException(422, "VALIDATION_ERROR", "Неизвестная сортировка")
    rows = (await db.execute(statement.offset((page - 1) * limit).limit(limit))).unique().all()
    return AdminUsersResponse(
        items=[
            admin_user_schema(user, searches, rag, saved, feedback)
            for user, searches, rag, saved, feedback in rows
        ],
        pagination=pagination(page, limit, total),
    )


async def get_admin_user(db: AsyncSession, user_id: UUID) -> AdminUserDetailOut:
    stats = stats_subqueries()
    row = (
        (await db.execute(user_statement().add_columns(*stats).where(User.id == user_id)))
        .unique()
        .one_or_none()
    )
    if row is None:
        raise ApiException(404, "NOT_FOUND", "Пользователь не найден")
    user, searches, rag, saved, feedback = row
    base = admin_user_schema(user, searches, rag, saved, feedback)
    history = (
        await db.scalars(
            select(SearchHistory)
            .where(SearchHistory.user_id == user.id)
            .order_by(SearchHistory.created_at.desc())
            .limit(10)
        )
    ).all()
    audit = (
        await db.scalars(
            select(AuditEvent)
            .where(
                or_(
                    AuditEvent.actor_user_id == user.id,
                    AuditEvent.entity_id == str(user.id),
                )
            )
            .order_by(AuditEvent.created_at.desc())
            .limit(10)
        )
    ).all()
    return AdminUserDetailOut(
        **base.model_dump(),
        recent_history=[history_schema(item) for item in history],
        recent_audit_events=[audit_to_schema(item) for item in audit],
    )


async def lock_admin_rule(db: AsyncSession) -> None:
    await db.execute(select(func.pg_advisory_xact_lock(LAST_ADMIN_LOCK_ID)))


async def active_admin_count(db: AsyncSession) -> int:
    return (
        await db.scalar(
            select(func.count())
            .select_from(User)
            .join(Role)
            .where(Role.code == UserRole.ADMIN, User.status == AccountStatus.ACTIVE)
        )
        or 0
    )


async def change_user_role(
    db: AsyncSession,
    request: Request,
    actor: User,
    target_id: UUID,
    role_code: UserRole,
) -> AdminUserOut:
    if target_id == actor.id:
        raise ApiException(409, "CONFLICT", "Нельзя изменить собственную роль")
    await lock_admin_rule(db)
    target = await get_user_by_id(db, target_id, lock=True)
    if target is None:
        raise ApiException(404, "NOT_FOUND", "Пользователь не найден")
    if target.role.code == UserRole.ADMIN and role_code != UserRole.ADMIN:
        if target.status == AccountStatus.ACTIVE and await active_admin_count(db) <= 1:
            raise ApiException(
                409, "CONFLICT", "Нельзя понизить последнего активного администратора"
            )
    role = await get_role(db, role_code.value)
    if role is None:
        raise ApiException(422, "VALIDATION_ERROR", "Неизвестная роль")
    before = target.role.code
    target.role = role
    target.account_version += 1
    now = utc_now()
    await revoke_user_sessions(db, target.id, now)
    await add_audit_event(
        db,
        request,
        actor=actor,
        action=AuditAction.CHANGE_USER_ROLE,
        entity_type=AuditEntityType.USER,
        entity_id=str(target.id),
        entity_label=target.email,
        summary="Изменена роль пользователя",
        before={"role": before},
        after={"role": role.code, "accountVersion": target.account_version},
    )
    await db.flush()
    return admin_user_schema(target, 0, 0, 0, 0)


async def block_user(
    db: AsyncSession,
    request: Request,
    actor: User,
    target_id: UUID,
    reason: str,
) -> AdminUserOut:
    if target_id == actor.id:
        raise ApiException(409, "CONFLICT", "Нельзя заблокировать самого себя")
    await lock_admin_rule(db)
    target = await get_user_by_id(db, target_id, lock=True)
    if target is None:
        raise ApiException(404, "NOT_FOUND", "Пользователь не найден")
    if target.role.code == UserRole.ADMIN and target.status == AccountStatus.ACTIVE:
        if await active_admin_count(db) <= 1:
            raise ApiException(
                409, "CONFLICT", "Нельзя заблокировать последнего активного администратора"
            )
    if target.status == AccountStatus.BLOCKED:
        return admin_user_schema(target, 0, 0, 0, 0)
    now = utc_now()
    target.status = AccountStatus.BLOCKED
    target.blocked_at = now
    target.blocked_by = actor.id
    target.block_reason = reason.strip()
    target.account_version += 1
    await revoke_user_sessions(db, target.id, now)
    await add_audit_event(
        db,
        request,
        actor=actor,
        action=AuditAction.BLOCK_USER,
        entity_type=AuditEntityType.USER,
        entity_id=str(target.id),
        entity_label=target.email,
        summary="Пользователь заблокирован",
        after={
            "status": target.status,
            "reason": target.block_reason,
            "accountVersion": target.account_version,
        },
    )
    await db.flush()
    return admin_user_schema(target, 0, 0, 0, 0)


async def unblock_user(
    db: AsyncSession, request: Request, actor: User, target_id: UUID
) -> AdminUserOut:
    target = await get_user_by_id(db, target_id, lock=True)
    if target is None:
        raise ApiException(404, "NOT_FOUND", "Пользователь не найден")
    if target.status == AccountStatus.ACTIVE:
        return admin_user_schema(target, 0, 0, 0, 0)
    target.status = AccountStatus.ACTIVE
    target.blocked_at = None
    target.blocked_by = None
    target.block_reason = None
    target.account_version += 1
    await add_audit_event(
        db,
        request,
        actor=actor,
        action=AuditAction.UNBLOCK_USER,
        entity_type=AuditEntityType.USER,
        entity_id=str(target.id),
        entity_label=target.email,
        summary="Пользователь разблокирован",
        after={"status": target.status, "accountVersion": target.account_version},
    )
    await db.flush()
    return admin_user_schema(target, 0, 0, 0, 0)
