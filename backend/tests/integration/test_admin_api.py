from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
from conftest import csrf_header, login
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AccountStatus, AuditAction, UserRole
from app.db.base import utc_now
from app.db.models.identity import Session, User
from app.db.models.operations import AuditEvent, Job, Source
from app.db.repositories.users import get_user_by_email
from app.main import app
from app.schemas.management import SourceUpdateRequest
from app.services.admin_sources import test_source_connection as check_source_connection
from app.services.admin_sources import update_source as update_source_service

pytestmark = pytest.mark.integration


async def test_admin_users_exclude_credentials_and_support_filters(client: AsyncClient) -> None:
    await login(client, "admin@pyanswer.local")
    response = await client.get(
        "/api/admin/users", params={"role": "EDITOR", "status": "ACTIVE", "limit": 5}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["pagination"]["total"] >= 3
    assert all(item["role"] == "EDITOR" for item in body["items"])
    serialized = response.text.casefold()
    assert all(part not in serialized for part in ("password", "digest", "salt", "session"))


async def test_admin_cannot_change_role_or_block_self(client: AsyncClient) -> None:
    admin = await login(client, "admin@pyanswer.local")
    user_id = admin["id"]
    role = await client.patch(
        f"/api/admin/users/{user_id}/role",
        json={"role": "USER"},
        headers=csrf_header(client),
    )
    block = await client.post(
        f"/api/admin/users/{user_id}/block",
        json={"reason": "Проверка запрета"},
        headers=csrf_header(client),
    )
    assert role.status_code == block.status_code == 409


async def test_role_change_revokes_target_sessions_and_creates_audit(
    client: AsyncClient, db: AsyncSession
) -> None:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as target_client:
        target = await login(target_client, "developer1@pyanswer.local")
        await login(client, "admin@pyanswer.local")
        response = await client.patch(
            f"/api/admin/users/{target['id']}/role",
            json={"role": "EDITOR"},
            headers=csrf_header(client),
        )
        assert response.status_code == 200
        assert response.json()["role"] == "EDITOR"
        assert (await target_client.get("/api/users/me")).status_code == 401

    sessions = (await db.scalars(select(Session).where(Session.user_id == target["id"]))).all()
    assert sessions and all(item.revoked_at is not None for item in sessions)
    audit = await db.scalar(
        select(AuditEvent).where(
            AuditEvent.action == AuditAction.CHANGE_USER_ROLE,
            AuditEvent.entity_id == target["id"],
        )
    )
    assert audit is not None


async def test_block_revokes_session_and_unblock_allows_login(
    client: AsyncClient, db: AsyncSession
) -> None:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as target_client:
        target = await login(target_client, "developer2@pyanswer.local")
        await login(client, "admin@pyanswer.local")
        blocked = await client.post(
            f"/api/admin/users/{target['id']}/block",
            json={"reason": "Нарушение правил"},
            headers=csrf_header(client),
        )
        assert blocked.status_code == 200
        assert blocked.json()["accountStatus"] == "BLOCKED"
        assert (await target_client.get("/api/users/me")).status_code == 401

        target_client.cookies.clear()
        csrf_response = await target_client.get("/api/auth/csrf")
        denied = await target_client.post(
            "/api/auth/login",
            json={"email": "developer2@pyanswer.local", "password": "Demo123!"},
            headers={"X-CSRF-Token": csrf_response.json()["csrfToken"]},
        )
        assert denied.status_code == 403

        unblocked = await client.post(
            f"/api/admin/users/{target['id']}/unblock", headers=csrf_header(client)
        )
        assert unblocked.status_code == 200
        assert unblocked.json()["accountStatus"] == "ACTIVE"

        target_client.cookies.clear()
        await login(target_client, "developer2@pyanswer.local")

    user = await get_user_by_email(db, "developer2@pyanswer.local")
    assert user is not None and user.account_version == 3
    actions = (
        await db.scalars(select(AuditEvent.action).where(AuditEvent.entity_id == str(user.id)))
    ).all()
    assert AuditAction.BLOCK_USER in actions and AuditAction.UNBLOCK_USER in actions


async def test_last_active_admin_rule_is_locked_and_enforced(db: AsyncSession) -> None:
    from app.services.admin_users import block_user, change_user_role

    active_admins = (
        await db.scalars(
            select(User)
            .join(User.role)
            .where(User.status == AccountStatus.ACTIVE, User.role.has(code=UserRole.ADMIN))
        )
    ).all()
    actor, target = active_admins[:2]
    actor.status = AccountStatus.BLOCKED
    await db.flush()
    request = Request({"type": "http", "method": "POST", "path": "/test", "headers": []})
    request.state.request_id = "last-admin-test"

    from app.api.errors import ApiException

    with pytest.raises(ApiException, match="последнего активного администратора"):
        await block_user(db, request, actor, target.id, "Проверка правила")
    with pytest.raises(ApiException, match="последнего активного администратора"):
        await change_user_role(db, request, actor, target.id, UserRole.USER)


async def test_source_sync_lifecycle_conflicts_and_permissions(client: AsyncClient) -> None:
    await login(client, "editor@pyanswer.local")
    assert (await client.get("/api/admin/sources")).status_code == 403

    client.cookies.clear()
    await login(client, "admin@pyanswer.local")
    source = (await client.get("/api/admin/sources")).json()["items"][0]
    source_id = source["id"]

    stopped = await client.post(f"/api/admin/sources/{source_id}/stop", headers=csrf_header(client))
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "CANCELLED"

    disabled = await client.patch(
        f"/api/admin/sources/{source_id}",
        json={"enabled": False},
        headers=csrf_header(client),
    )
    assert disabled.status_code == 200
    denied = await client.post(f"/api/admin/sources/{source_id}/sync", headers=csrf_header(client))
    assert denied.status_code == 409

    enabled = await client.patch(
        f"/api/admin/sources/{source_id}",
        json={"enabled": True, "pageSize": 50, "targetDocuments": 10000},
        headers=csrf_header(client),
    )
    assert enabled.status_code == 200
    started = await client.post(f"/api/admin/sources/{source_id}/sync", headers=csrf_header(client))
    assert started.status_code == 200
    assert started.json()["type"] == "SOURCE_SYNC"
    duplicate = await client.post(
        f"/api/admin/sources/{source_id}/sync", headers=csrf_header(client)
    )
    assert duplicate.status_code == 409


async def test_source_connection_uses_safe_mocked_http(db: AsyncSession) -> None:
    actor = await get_user_by_email(db, "admin@pyanswer.local")
    source = await db.scalar(select(Source).limit(1))
    assert actor is not None and source is not None
    request = Request({"type": "http", "method": "POST", "path": "/test", "headers": []})
    request.state.request_id = "source-test"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.stackexchange.com"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "question_id": 1,
                        "creation_date": 1_700_000_000,
                        "last_activity_date": 1_700_000_100,
                    }
                ],
                "has_more": False,
                "quota_max": 300,
                "quota_remaining": 250,
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as mocked_client:
        result = await check_source_connection(db, request, actor, source.id, mocked_client)
    assert result.success is True


async def test_source_update_service_disables_idle_source(db: AsyncSession) -> None:
    actor = await get_user_by_email(db, "admin@pyanswer.local")
    source = await db.scalar(select(Source).limit(1))
    assert actor is not None and source is not None
    source.current_job_id = None
    source.status = "IDLE"
    active = (
        await db.scalars(
            select(Job).where(
                Job.source_id == source.id,
                Job.status.in_(["QUEUED", "RUNNING"]),
            )
        )
    ).all()
    for job in active:
        job.status = "CANCELLED"
        job.cancellable = False
    await db.flush()
    request = Request({"type": "http", "method": "PATCH", "path": "/test", "headers": []})
    request.state.request_id = "source-update-test"
    result = await update_source_service(
        db, request, actor, source.id, SourceUpdateRequest(enabled=False)
    )
    assert result.enabled is False
    assert result.status == "DISABLED"


async def test_admin_jobs_cancel_retry_and_full_reindex_conflicts(client: AsyncClient) -> None:
    await login(client, "admin@pyanswer.local")
    jobs = (await client.get("/api/admin/jobs", params={"limit": 100})).json()["items"]
    completed = next(item for item in jobs if item["status"] == "COMPLETED")
    failed = next(item for item in jobs if item["status"] == "FAILED")
    running = next(item for item in jobs if item["status"] == "RUNNING")

    assert (
        await client.post(f"/api/admin/jobs/{completed['id']}/cancel", headers=csrf_header(client))
    ).status_code == 409
    assert (
        await client.post(f"/api/admin/jobs/{running['id']}/retry", headers=csrf_header(client))
    ).status_code == 409

    source_id = running["sourceId"]
    await client.post(f"/api/admin/sources/{source_id}/stop", headers=csrf_header(client))
    retried = await client.post(
        f"/api/admin/jobs/{failed['id']}/retry", headers=csrf_header(client)
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["retryOfJobId"] == failed["id"]

    await client.post(f"/api/admin/sources/{source_id}/stop", headers=csrf_header(client))
    full = await client.post("/api/admin/jobs/full-reindex", headers=csrf_header(client))
    assert full.status_code == 200
    assert (
        await client.post("/api/admin/jobs/full-reindex", headers=csrf_header(client))
    ).status_code == 409


async def test_audit_is_admin_read_only_and_sanitized(client: AsyncClient) -> None:
    await login(client, "editor@pyanswer.local")
    assert (await client.get("/api/admin/audit")).status_code == 403

    client.cookies.clear()
    await login(client, "admin@pyanswer.local")
    response = await client.get("/api/admin/audit")
    assert response.status_code == 200
    event_id = response.json()["items"][0]["id"]
    detail = await client.get(f"/api/admin/audit/{event_id}")
    assert detail.status_code == 200
    assert all(
        part not in detail.text.casefold()
        for part in ("passwordhash", "sessiontoken", "csrf_token")
    )
    assert (
        await client.delete(f"/api/admin/audit/{event_id}", headers=csrf_header(client))
    ).status_code == 405
    assert (
        await client.patch(f"/api/admin/audit/{event_id}", json={}, headers=csrf_header(client))
    ).status_code == 405


async def test_system_status_health_check_and_settings_are_admin_only(
    client: AsyncClient, db: AsyncSession
) -> None:
    await login(client, "editor@pyanswer.local")
    assert (await client.get("/api/admin/system/settings")).status_code == 403

    client.cookies.clear()
    await login(client, "admin@pyanswer.local")
    status = await client.get("/api/admin/system")
    assert status.status_code == 200
    services = {item["id"]: item for item in status.json()["services"]}
    assert services["backend"]["status"] == "ONLINE"
    assert services["qdrant"]["status"] == "OFFLINE"
    before = status.json()["lastCheckAt"]

    checked = await client.post("/api/admin/system/health-check", headers=csrf_header(client))
    assert checked.status_code == 200
    assert checked.json()["lastCheckAt"] >= before
    audit_count = await db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.action == AuditAction.HEALTH_CHECK)
    )
    assert audit_count == 1

    invalid = await client.patch(
        "/api/admin/system/settings",
        json={"ragSourcesLimit": 0},
        headers=csrf_header(client),
    )
    assert invalid.status_code == 422
    updated = await client.patch(
        "/api/admin/system/settings",
        json={"allowGuestSearch": False, "allowGuestRag": False, "ragSourcesLimit": 3},
        headers=csrf_header(client),
    )
    assert updated.status_code == 200
    assert updated.json()["allowGuestSearch"] is False


async def test_expired_sessions_are_not_returned_as_current_user(
    client: AsyncClient, db: AsyncSession
) -> None:
    await login(client)
    session = await db.scalar(select(Session).order_by(Session.created_at.desc()))
    assert session is not None
    session.expires_at = utc_now() - timedelta(minutes=1)
    await db.commit()
    assert (await client.get("/api/auth/me")).json() is None
