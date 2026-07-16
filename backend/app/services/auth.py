from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from anyio import to_thread
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiException
from app.core.config import Settings, get_settings
from app.core.enums import AccountStatus, AuditAction, AuditEntityType, UserRole
from app.core.security import PasswordService, generate_opaque_token, hash_token
from app.db.base import utc_now
from app.db.models.identity import Session, User, UserPreference
from app.db.repositories.users import get_role, get_user_by_email, normalize_email
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services.audit import add_audit_event


@dataclass(slots=True)
class AuthResult:
    user: User
    session_token: str
    csrf_token: str
    max_age: int | None


async def create_session(
    db: AsyncSession,
    request: Request,
    user: User,
    *,
    remember: bool,
    settings: Settings | None = None,
) -> AuthResult:
    config = settings or get_settings()
    session_token = generate_opaque_token()
    csrf_token = generate_opaque_token()
    now = utc_now()
    ttl = (
        timedelta(days=config.remember_session_ttl_days)
        if remember
        else timedelta(hours=config.session_ttl_hours)
    )
    client = request.client
    record = Session(
        user_id=user.id,
        token_hash=hash_token(session_token),
        csrf_token_hash=hash_token(csrf_token),
        account_version=user.account_version,
        remember_me=remember,
        created_at=now,
        last_seen_at=now,
        expires_at=now + ttl,
        ip_address=client.host if client else None,
        user_agent=request.headers.get("user-agent", "")[:500] or None,
    )
    db.add(record)
    await db.flush()
    return AuthResult(
        user=user,
        session_token=session_token,
        csrf_token=csrf_token,
        max_age=int(ttl.total_seconds()) if remember else None,
    )


async def register_user(db: AsyncSession, request: Request, payload: RegisterRequest) -> AuthResult:
    if await get_user_by_email(db, str(payload.email)):
        raise ApiException(409, "CONFLICT", "Пользователь с таким email уже существует")
    role = await get_role(db, UserRole.USER.value)
    if role is None:
        raise ApiException(500, "INTERNAL_ERROR", "Справочник ролей не инициализирован")
    password_service = PasswordService.from_settings()
    try:
        password_hash = await to_thread.run_sync(password_service.hash, payload.password)
    except ValueError as exc:
        raise ApiException(422, "VALIDATION_ERROR", str(exc)) from exc
    now = utc_now()
    user = User(
        role=role,
        name=payload.display_name,
        email=str(payload.email).strip(),
        normalized_email=normalize_email(str(payload.email)),
        password_hash=password_hash,
        status=AccountStatus.ACTIVE,
        account_version=1,
        registered_at=now,
        last_active_at=now,
        preferences=UserPreference(),
    )
    db.add(user)
    await db.flush()
    await add_audit_event(
        db,
        request,
        actor=user,
        action=AuditAction.REGISTER,
        entity_type=AuditEntityType.AUTH,
        entity_id=str(user.id),
        entity_label=user.email,
        summary="Создана учётная запись пользователя",
        after={"id": str(user.id), "email": user.email, "role": role.code},
    )
    return await create_session(db, request, user, remember=payload.remember)


async def login_user(db: AsyncSession, request: Request, payload: LoginRequest) -> AuthResult:
    user = await get_user_by_email(db, str(payload.email))
    if user is None:
        raise ApiException(401, "UNAUTHORIZED", "Неверный email или пароль")
    password_service = PasswordService.from_settings()
    valid = await to_thread.run_sync(password_service.verify, user.password_hash, payload.password)
    if not valid:
        raise ApiException(401, "UNAUTHORIZED", "Неверный email или пароль")
    if user.status != AccountStatus.ACTIVE:
        raise ApiException(403, "FORBIDDEN", "Учётная запись заблокирована")
    if password_service.needs_rehash(user.password_hash):
        user.password_hash = await to_thread.run_sync(password_service.hash, payload.password)
    user.last_active_at = utc_now()
    await add_audit_event(
        db,
        request,
        actor=user,
        action=AuditAction.LOGIN,
        entity_type=AuditEntityType.AUTH,
        entity_id=str(user.id),
        entity_label=user.email,
        summary="Выполнен вход в систему",
    )
    return await create_session(db, request, user, remember=payload.remember)
