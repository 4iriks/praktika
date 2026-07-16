from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiException
from app.core.config import get_settings
from app.core.enums import AccountStatus, Permission
from app.core.security import constant_time_equal, hash_token
from app.db.base import utc_now
from app.db.models.identity import Session, User
from app.db.repositories.sessions import get_session_by_hash
from app.db.session import get_db_session

DB = Annotated[AsyncSession, Depends(get_db_session)]


async def get_optional_user(request: Request, db: DB) -> User | None:
    settings = get_settings()
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        return None
    record = await get_session_by_hash(db, hash_token(raw_token))
    now = utc_now()
    if record is None or record.revoked_at is not None or record.expires_at <= now:
        return None
    user = record.user
    if user.status != AccountStatus.ACTIVE or record.account_version != user.account_version:
        record.revoked_at = now
        return None
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        csrf_hash = getattr(request.state, "csrf_hash", "")
        if not csrf_hash or not constant_time_equal(record.csrf_token_hash, csrf_hash):
            raise ApiException(403, "CSRF_INVALID", "CSRF-токен сессии недействителен")
    record.last_seen_at = now
    request.state.user_id = user.id
    request.state.auth_session = record
    return user


async def get_current_user(user: Annotated[User | None, Depends(get_optional_user)]) -> User:
    if user is None:
        raise ApiException(401, "UNAUTHORIZED", "Требуется авторизация")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]


def require_permission(permission: Permission) -> Callable[..., object]:
    async def dependency(user: CurrentUser) -> User:
        codes = {item.code for item in user.role.permissions}
        if permission.value not in codes:
            raise ApiException(403, "FORBIDDEN", "Недостаточно прав")
        return user

    return dependency


def require_any_permission(*permissions: Permission) -> Callable[..., object]:
    async def dependency(user: CurrentUser) -> User:
        codes = {item.code for item in user.role.permissions}
        if not any(permission.value in codes for permission in permissions):
            raise ApiException(403, "FORBIDDEN", "Недостаточно прав")
        return user

    return dependency


def require_all_permissions(*permissions: Permission) -> Callable[..., object]:
    async def dependency(user: CurrentUser) -> User:
        codes = {item.code for item in user.role.permissions}
        if not all(permission.value in codes for permission in permissions):
            raise ApiException(403, "FORBIDDEN", "Недостаточно прав")
        return user

    return dependency


def current_session(request: Request) -> Session:
    record = getattr(request.state, "auth_session", None)
    if not isinstance(record, Session):
        raise ApiException(401, "UNAUTHORIZED", "Требуется авторизация")
    return record
