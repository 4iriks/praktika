from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from conftest import csrf_header, login
from fastapi import Request
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiException
from app.db.models.operations import Job, Source
from app.db.repositories.users import get_user_by_email
from app.schemas.management import SourceUpdateRequest
from app.services.admin_sources import test_source_connection as check_source_connection
from app.services.admin_sources import update_source

pytestmark = pytest.mark.integration


async def test_user_history_saved_and_feedback_filter_branches(client: AsyncClient) -> None:
    await login(client)
    history = await client.get(
        "/api/history",
        params={
            "search": "async",
            "view": "documents",
            "mode": "hybrid",
            "date_sort": "oldest",
            "date_from": "2020-01-01T00:00:00Z",
            "date_to": "2030-01-01T00:00:00Z",
        },
    )
    assert history.status_code == 200
    assert all(item["view"] == "documents" for item in history.json()["items"])

    saved = await client.get("/api/saved")
    tag = saved.json()["availableTags"][0]["slug"]
    for sort in ("score", "publishedAt", "savedAt"):
        response = await client.get(
            "/api/saved", params={"search": "Python", "tags": tag, "sort": sort}
        )
        assert response.status_code == 200

    feedback = await client.get("/api/feedback/by-response/seed-response-1")
    missing = await client.get("/api/feedback/by-response/missing-response")
    assert feedback.status_code == 200 and feedback.json()["value"] == "positive"
    assert missing.status_code == 200 and missing.json() is None


async def test_editor_document_and_job_filter_branches(client: AsyncClient) -> None:
    await login(client, "editor@pyanswer.local")
    first = (await client.get("/api/editor/documents", params={"limit": 1})).json()["items"][0]
    source_id = first["sourceId"]
    tag = first["managedTags"][0]
    params = {
        "q": first["original"]["title"].split()[0],
        "status": first["status"],
        "tags": tag,
        "accepted": "true" if first["original"]["answers"] else "all",
        "has_code": "true",
        "bm25": first["bm25Status"],
        "vector": first["vectorStatus"],
        "source": source_id,
        "updated_after": "2020-01-01T00:00:00Z",
    }
    assert (await client.get("/api/editor/documents", params=params)).status_code == 200
    for sort in ("updated_asc", "rating_desc", "title_asc", "status_asc"):
        assert (
            await client.get("/api/editor/documents", params={"sort": sort, "limit": 2})
        ).status_code == 200
    assert (await client.get("/api/editor/documents?sort=unknown")).status_code == 422

    jobs = (await client.get("/api/editor/jobs", params={"limit": 100})).json()["items"]
    related = next(item for item in jobs if item["documentId"] is not None)
    filters = {
        "id": related["id"],
        "type": related["type"],
        "status": related["status"],
        "stage": related["stage"],
        "document_id": related["documentId"],
        "source": related["sourceId"],
        "date_from": "2020-01-01T00:00:00Z",
        "date_to": "2030-01-01T00:00:00Z",
        "sort": "progress_desc",
    }
    filtered = await client.get("/api/editor/jobs", params=filters)
    assert filtered.status_code == 200
    assert len(filtered.json()["items"]) == 1
    assert (await client.get("/api/editor/jobs?sort=created_asc")).status_code == 200


async def test_admin_user_and_audit_filter_branches(client: AsyncClient) -> None:
    admin = await login(client, "admin@pyanswer.local")
    for sort in ("created_asc", "activity_desc", "name_asc"):
        response = await client.get(
            "/api/admin/users",
            params={
                "q": "pyanswer",
                "registered_from": "2020-01-01T00:00:00Z",
                "registered_to": "2030-01-01T00:00:00Z",
                "sort": sort,
            },
        )
        assert response.status_code == 200
    assert (await client.get(f"/api/admin/users/{uuid4()}")).status_code == 404

    audit = (await client.get("/api/admin/audit", params={"limit": 1})).json()["items"][0]
    filters = {
        "q": audit["requestId"],
        "actor": admin["id"],
        "role": "ADMIN",
        "action": audit["action"],
        "entity_type": audit["entityType"],
        "outcome": audit["outcome"],
        "date_from": "2020-01-01T00:00:00Z",
        "date_to": "2030-01-01T00:00:00Z",
        "sort": "created_asc",
    }
    response = await client.get("/api/admin/audit", params=filters)
    assert response.status_code == 200
    assert response.json()["items"]
    assert (
        await client.get("/api/admin/audit", params={"actor": "Администратор"})
    ).status_code == 200
    assert (await client.get("/api/admin/audit?sort=unknown")).status_code == 422
    assert (await client.get(f"/api/admin/audit/{uuid4()}")).status_code == 404


async def test_admin_source_error_and_job_action_branches(
    client: AsyncClient, db: AsyncSession
) -> None:
    await login(client, "admin@pyanswer.local")
    sources = await client.get(
        "/api/admin/sources", params={"q": "Stack", "status": "SYNCING", "enabled": "true"}
    )
    assert sources.status_code == 200
    source_id = sources.json()["items"][0]["id"]

    conflict = await client.patch(
        f"/api/admin/sources/{source_id}",
        json={"enabled": False},
        headers=csrf_header(client),
    )
    assert conflict.status_code == 409
    assert (
        await client.post(f"/api/admin/sources/{source_id}/stop", headers=csrf_header(client))
    ).status_code == 200
    assert (
        await client.post(f"/api/admin/sources/{source_id}/stop", headers=csrf_header(client))
    ).status_code == 200
    assert (await client.get(f"/api/admin/sources/{uuid4()}")).status_code == 404

    jobs = (await client.get("/api/admin/jobs", params={"limit": 100})).json()["items"]
    queued = next(item for item in jobs if item["status"] == "QUEUED")
    assert (await client.get(f"/api/admin/jobs/{queued['id']}")).status_code == 200
    cancelled = await client.post(
        f"/api/admin/jobs/{queued['id']}/cancel", headers=csrf_header(client)
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    assert (
        await client.post(f"/api/admin/jobs/{queued['id']}/cancel", headers=csrf_header(client))
    ).status_code == 409
    assert (await client.get(f"/api/admin/jobs/{uuid4()}")).status_code == 404

    actor = await get_user_by_email(db, "admin@pyanswer.local")
    source = await db.get(Source, UUID(source_id))
    assert actor is not None and source is not None
    source.base_url = "https://example.com"
    await db.flush()
    request = Request({"type": "http", "method": "POST", "path": "/test", "headers": []})
    request.state.request_id = "source-allowlist-test"
    with pytest.raises(ApiException) as exc_info:
        await check_source_connection(db, request, actor, source.id)
    assert exc_info.value.code == "VALIDATION_ERROR"


async def test_source_update_idempotent_enable_and_user_admin_idempotency(
    db: AsyncSession,
) -> None:
    actor = await get_user_by_email(db, "admin@pyanswer.local")
    blocked = await get_user_by_email(db, "developer4@pyanswer.local")
    source = await db.scalar(select(Source).limit(1))
    assert actor is not None and blocked is not None and source is not None
    request = Request({"type": "http", "method": "PATCH", "path": "/test", "headers": []})
    request.state.request_id = "branch-test"

    source.status = "DISABLED"
    source.enabled = False
    active_jobs = (
        await db.scalars(
            select(Job).where(Job.source_id == source.id, Job.status.in_(["QUEUED", "RUNNING"]))
        )
    ).all()
    for job in active_jobs:
        job.status = "CANCELLED"
    await db.flush()
    enabled = await update_source(db, request, actor, source.id, SourceUpdateRequest(enabled=True))
    assert enabled.status == "IDLE"

    from app.services.admin_users import block_user, unblock_user

    same_blocked = await block_user(db, request, actor, blocked.id, "Повтор")
    assert same_blocked.account_status == "BLOCKED"
    active = await unblock_user(db, request, actor, blocked.id)
    same_active = await unblock_user(db, request, actor, blocked.id)
    assert active.account_status == same_active.account_status == "ACTIVE"
