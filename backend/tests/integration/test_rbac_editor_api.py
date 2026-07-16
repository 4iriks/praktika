from __future__ import annotations

from uuid import uuid4

import pytest
from conftest import csrf_header, login
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AuditAction, DocumentStatus, JobStatus, JobType
from app.db.models.content import Document
from app.db.models.operations import AuditEvent, Job

pytestmark = pytest.mark.integration


async def document_without_active_reindex(db: AsyncSession) -> Document:
    active_jobs = select(Job.document_id).where(
        Job.type == JobType.DOCUMENT_REINDEX,
        Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
    )
    document = await db.scalar(
        select(Document).where(
            Document.status == DocumentStatus.ACTIVE,
            Document.id.not_in(active_jobs),
        )
    )
    assert document is not None
    return document


@pytest.mark.parametrize("path", ["/api/editor/dashboard", "/api/admin/dashboard"])
async def test_guest_gets_401_for_management_routes(client: AsyncClient, path: str) -> None:
    response = await client.get(path)
    assert response.status_code == 401


async def test_user_cannot_call_editor_or_admin_even_with_role_injection(
    client: AsyncClient,
) -> None:
    await login(client)
    editor = await client.get("/api/editor/documents?role=ADMIN", headers={"X-Role": "ADMIN"})
    admin = await client.get("/api/admin/users?permission=USERS_MANAGE")
    assert editor.status_code == admin.status_code == 403


async def test_editor_can_use_editor_but_not_admin(client: AsyncClient) -> None:
    await login(client, "editor@pyanswer.local")
    dashboard = await client.get("/api/editor/dashboard")
    documents = await client.get("/api/editor/documents", params={"limit": 5})
    admin = await client.get("/api/admin/users")

    assert dashboard.status_code == 200
    assert dashboard.json()["totalDocuments"] == 20
    assert documents.status_code == 200
    assert documents.json()["pagination"]["total"] == 20
    assert admin.status_code == 403


async def test_admin_inherits_editor_and_admin_permissions(client: AsyncClient) -> None:
    body = await login(client, "admin@pyanswer.local")
    assert "MANAGED_DOCUMENTS_VIEW" in body["permissions"]
    assert "USERS_MANAGE" in body["permissions"]
    assert (await client.get("/api/editor/dashboard")).status_code == 200
    assert (await client.get("/api/admin/dashboard")).status_code == 200


async def test_metadata_update_normalizes_tags_increments_version_and_preserves_source(
    client: AsyncClient, db: AsyncSession
) -> None:
    await login(client, "editor@pyanswer.local")
    document = await document_without_active_reindex(db)
    original_question = document.question_text
    original_url = document.source_url
    original_version = document.version
    document_id = document.id

    response = await client.patch(
        f"/api/editor/documents/{document.id}/metadata",
        json={
            "normalizedTitle": "  Новый редакторский заголовок  ",
            "managedTags": [" AsyncIO ", "asyncio", " PYTHON "],
            "editorialNote": "  Проверено редактором  ",
        },
        headers=csrf_header(client),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["normalizedTitle"] == "Новый редакторский заголовок"
    assert body["managedTags"] == ["asyncio", "python"]
    assert body["editorialNote"] == "Проверено редактором"
    assert body["version"] == original_version + 1

    db.expire_all()
    persisted = await db.get(Document, document_id)
    assert persisted is not None
    assert persisted.question_text == original_question
    assert persisted.source_url == original_url
    audit_count = await db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.entity_id == str(document_id),
            AuditEvent.action == AuditAction.UPDATE_DOCUMENT_METADATA,
        )
    )
    assert audit_count == 1


async def test_hide_requires_reason_removes_public_document_and_restore_returns_it(
    client: AsyncClient, db: AsyncSession
) -> None:
    await login(client, "editor@pyanswer.local")
    document = await document_without_active_reindex(db)
    path = f"/api/editor/documents/{document.id}"

    invalid = await client.post(f"{path}/hide", json={"reason": " "}, headers=csrf_header(client))
    assert invalid.status_code == 422
    hidden = await client.post(
        f"{path}/hide",
        json={"reason": "Требуется модерация"},
        headers=csrf_header(client),
    )
    assert hidden.status_code == 200
    assert hidden.json()["status"] == "HIDDEN"
    assert (await client.get(f"/api/documents/{document.id}")).status_code == 404

    restored = await client.post(f"{path}/restore", headers=csrf_header(client))
    assert restored.status_code == 200
    assert restored.json()["status"] == "ACTIVE"
    assert (await client.get(f"/api/documents/{document.id}")).status_code == 200


async def test_reindex_creates_one_queued_job_and_conflicts_on_duplicate(
    client: AsyncClient, db: AsyncSession
) -> None:
    await login(client, "editor@pyanswer.local")
    document = await document_without_active_reindex(db)
    url = f"/api/editor/documents/{document.id}/reindex"

    created = await client.post(url, headers=csrf_header(client))
    assert created.status_code == 200, created.text
    assert created.json()["type"] == "DOCUMENT_REINDEX"
    assert created.json()["status"] == "QUEUED"
    duplicate = await client.post(url, headers=csrf_header(client))
    assert duplicate.status_code == 409
    count = await db.scalar(
        select(func.count())
        .select_from(Job)
        .where(
            Job.document_id == document.id,
            Job.type == JobType.DOCUMENT_REINDEX,
            Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        )
    )
    assert count == 1


async def test_bulk_action_returns_partial_result_and_single_batch_audit(
    client: AsyncClient, db: AsyncSession
) -> None:
    await login(client, "editor@pyanswer.local")
    active = await document_without_active_reindex(db)
    hidden = await db.scalar(select(Document).where(Document.status == DocumentStatus.HIDDEN))
    assert hidden is not None
    missing = uuid4()

    response = await client.post(
        "/api/editor/documents/bulk",
        json={
            "documentIds": [str(active.id), str(hidden.id), str(missing)],
            "action": "HIDE",
            "reason": "Пакетная модерация",
        },
        headers=csrf_header(client),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["successCount"] == 1
    assert body["skippedCount"] == 1
    assert body["failedCount"] == 1
    assert {item["outcome"] for item in body["items"]} == {"SUCCESS", "SKIPPED", "FAILED"}

    batches = await db.scalar(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.batch_id == body["batchId"])
    )
    assert batches == 1


async def test_bulk_rejects_more_than_one_hundred_documents(client: AsyncClient) -> None:
    await login(client, "editor@pyanswer.local")
    response = await client.post(
        "/api/editor/documents/bulk",
        json={"documentIds": [str(uuid4()) for _ in range(101)], "action": "RESTORE"},
        headers=csrf_header(client),
    )
    assert response.status_code == 422


async def test_editor_job_filters_validate_sort_and_dates(client: AsyncClient) -> None:
    await login(client, "editor@pyanswer.local")
    filtered = await client.get(
        "/api/editor/jobs",
        params={"status": "FAILED", "date_from": "2020-01-01T00:00:00Z"},
    )
    assert filtered.status_code == 200
    assert all(item["status"] == "FAILED" for item in filtered.json()["items"])
    assert (await client.get("/api/editor/jobs?sort=unknown")).status_code == 422
    assert (await client.get("/api/editor/jobs?date_from=bad")).status_code == 422
