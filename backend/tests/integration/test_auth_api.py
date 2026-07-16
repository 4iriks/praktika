from __future__ import annotations

from datetime import timedelta

import pytest
from conftest import csrf, csrf_header, login
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import InMemoryRateLimiter
from app.core.security import hash_token
from app.db.base import utc_now
from app.db.models.identity import Session, User
from app.db.repositories.users import get_user_by_email

pytestmark = pytest.mark.integration


async def test_csrf_is_required_and_validated(client: AsyncClient) -> None:
    payload = {"email": "user@pyanswer.local", "password": "Demo123!"}
    missing = await client.post("/api/auth/login", json=payload)
    assert missing.status_code == 403
    assert missing.json()["error"]["code"] == "CSRF_INVALID"

    token = await csrf(client)
    wrong = await client.post(
        "/api/auth/login", json=payload, headers={"X-CSRF-Token": f"{token}-wrong"}
    )
    assert wrong.status_code == 403

    valid = await client.post("/api/auth/login", json=payload, headers={"X-CSRF-Token": token})
    assert valid.status_code == 200
    assert valid.json()["role"] == "USER"


async def test_registration_creates_only_user_and_casefolds_email(client: AsyncClient) -> None:
    token = await csrf(client)
    payload = {
        "displayName": "Новый пользователь",
        "email": "New.User@example.com",
        "password": "Strong123",
        "acceptedTerms": True,
        "remember": True,
    }
    created = await client.post("/api/auth/register", json=payload, headers={"X-CSRF-Token": token})
    assert created.status_code == 201
    body = created.json()
    assert body["role"] == "USER"
    assert "password" not in body and "passwordHash" not in body
    assert "pyanswer_session" in created.cookies
    assert "HttpOnly" in created.headers["set-cookie"]

    duplicate_token = created.cookies["pyanswer_csrf"]
    duplicate = await client.post(
        "/api/auth/register",
        json={**payload, "email": "new.user@example.com"},
        headers={"X-CSRF-Token": duplicate_token},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "CONFLICT"


async def test_registration_rejects_role_and_weak_password(client: AsyncClient) -> None:
    token = await csrf(client)
    base = {
        "displayName": "Новый пользователь",
        "email": "new@example.com",
        "password": "weakpass",
        "acceptedTerms": True,
    }
    weak = await client.post("/api/auth/register", json=base, headers={"X-CSRF-Token": token})
    assert weak.status_code == 422

    injected = await client.post(
        "/api/auth/register",
        json={**base, "password": "Strong123", "role": "ADMIN"},
        headers={"X-CSRF-Token": token},
    )
    assert injected.status_code == 422


async def test_login_cookie_stores_only_hash_and_neutral_error(
    client: AsyncClient, db: AsyncSession
) -> None:
    bad_token = await csrf(client)
    bad = await client.post(
        "/api/auth/login",
        json={"email": "missing@example.com", "password": "Wrong123"},
        headers={"X-CSRF-Token": bad_token},
    )
    assert bad.status_code == 401
    assert bad.json()["error"]["message"] == "Неверный email или пароль"

    await login(client)
    raw_token = client.cookies["pyanswer_session"]
    record = await db.scalar(select(Session).where(Session.token_hash == hash_token(raw_token)))
    assert record is not None
    assert record.token_hash != raw_token
    assert len(record.token_hash) == 64

    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "user@pyanswer.local"
    assert all(key not in me.json() for key in ("password", "passwordHash", "salt"))


@pytest.mark.parametrize("state", ["expired", "revoked", "version"])
async def test_invalid_session_cannot_access_protected_api(
    state: str, client: AsyncClient, db: AsyncSession
) -> None:
    await login(client)
    raw_token = client.cookies["pyanswer_session"]
    record = await db.scalar(select(Session).where(Session.token_hash == hash_token(raw_token)))
    assert record is not None
    if state == "expired":
        record.expires_at = utc_now() - timedelta(seconds=1)
    elif state == "revoked":
        record.revoked_at = utc_now()
    else:
        user = await db.get(User, record.user_id)
        assert user is not None
        user.account_version += 1
    await db.commit()

    response = await client.get("/api/users/me")
    assert response.status_code == 401


async def test_blocked_user_cannot_login(client: AsyncClient) -> None:
    token = await csrf(client)
    response = await client.post(
        "/api/auth/login",
        json={"email": "developer4@pyanswer.local", "password": "Demo123!"},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_logout_requires_csrf_and_revokes_session(
    client: AsyncClient, db: AsyncSession
) -> None:
    await login(client)
    raw_token = client.cookies["pyanswer_session"]

    missing = await client.post("/api/auth/logout")
    assert missing.status_code == 403

    response = await client.post("/api/auth/logout", headers=csrf_header(client))
    assert response.status_code == 204
    db.expire_all()
    record = await db.scalar(select(Session).where(Session.token_hash == hash_token(raw_token)))
    assert record is not None and record.revoked_at is not None


async def test_request_id_security_headers_and_error_envelope(client: AsyncClient) -> None:
    response = await client.get("/api/users/me", headers={"X-Request-ID": "test-request-42"})
    assert response.status_code == 401
    assert response.headers["X-Request-ID"] == "test-request-42"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.json() == {
        "error": {
            "code": "UNAUTHORIZED",
            "message": "Требуется авторизация",
            "details": {},
            "requestId": "test-request-42",
        }
    }


async def test_unknown_cors_origin_is_not_allowed(client: AsyncClient) -> None:
    response = await client.options(
        "/api/auth/login",
        headers={
            "Origin": "https://attacker.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.headers.get("access-control-allow-origin") is None


def test_rate_limiter_returns_429_after_limit() -> None:
    limiter = InMemoryRateLimiter(limit=1, window_seconds=60, enabled=True)
    limiter.check("login:127.0.0.1")
    with pytest.raises(Exception) as exc_info:
        limiter.check("login:127.0.0.1")
    assert getattr(exc_info.value, "status", None) == 429


async def test_email_normalization_is_persisted(db: AsyncSession) -> None:
    user = await get_user_by_email(db, " USER@PYANSWER.LOCAL ")
    assert user is not None
    assert user.normalized_email == "user@pyanswer.local"
