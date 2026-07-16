from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.api.dependencies import DB, OptionalUser, current_session, get_current_user
from app.core.config import get_settings
from app.core.csrf import clear_csrf_cookie, set_csrf_cookie
from app.core.enums import AuditAction, AuditEntityType
from app.core.rate_limit import InMemoryRateLimiter
from app.core.security import generate_opaque_token, hash_token
from app.db.base import utc_now
from app.db.models.identity import User
from app.schemas.auth import CSRFResponse, LoginRequest, RegisterRequest, UserOut
from app.services.audit import add_audit_event
from app.services.auth import AuthResult, login_user, register_user
from app.services.serializers import user_to_schema

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()
auth_rate_limiter = InMemoryRateLimiter(
    limit=settings.auth_rate_limit_requests,
    window_seconds=settings.auth_rate_limit_window_seconds,
    enabled=settings.app_env != "test",
)


def client_key(request: Request, action: str) -> str:
    host = request.client.host if request.client else "local"
    return f"{action}:{host}"


def set_auth_cookies(response: Response, result: AuthResult) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        result.session_token,
        max_age=result.max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )
    set_csrf_cookie(response, result.csrf_token, settings)


@router.get(
    "/csrf",
    response_model=CSRFResponse,
    summary="Получить CSRF-токен",
    operation_id="getCsrfToken",
)
async def csrf_token(
    response: Response, request: Request, db: DB, user: OptionalUser
) -> CSRFResponse:
    token = generate_opaque_token()
    if user is not None:
        current_session(request).csrf_token_hash = hash_token(token)
    set_csrf_cookie(response, token, settings)
    return CSRFResponse(csrf_token=token)


@router.post(
    "/register",
    response_model=UserOut,
    status_code=201,
    summary="Зарегистрировать пользователя",
    operation_id="register",
)
async def register(
    payload: RegisterRequest, request: Request, response: Response, db: DB
) -> UserOut:
    auth_rate_limiter.check(client_key(request, "register"))
    result = await register_user(db, request, payload)
    set_auth_cookies(response, result)
    return user_to_schema(result.user)


@router.post(
    "/login",
    response_model=UserOut,
    summary="Войти в систему",
    operation_id="login",
)
async def login(payload: LoginRequest, request: Request, response: Response, db: DB) -> UserOut:
    auth_rate_limiter.check(client_key(request, "login"))
    result = await login_user(db, request, payload)
    set_auth_cookies(response, result)
    return user_to_schema(result.user)


@router.post(
    "/logout",
    status_code=204,
    summary="Завершить текущую сессию",
    operation_id="logout",
)
async def logout(
    request: Request,
    response: Response,
    db: DB,
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    session = current_session(request)
    session.revoked_at = utc_now()
    await add_audit_event(
        db,
        request,
        actor=user,
        action=AuditAction.LOGOUT,
        entity_type=AuditEntityType.AUTH,
        entity_id=str(user.id),
        entity_label=user.email,
        summary="Текущая сессия завершена",
    )
    response.delete_cookie(
        settings.session_cookie_name, path="/", samesite=settings.cookie_samesite
    )
    clear_csrf_cookie(response, settings)


@router.get(
    "/me",
    response_model=UserOut | None,
    summary="Получить текущего пользователя",
    operation_id="getCurrentUser",
)
async def me(user: OptionalUser) -> UserOut | None:
    return user_to_schema(user) if user else None
