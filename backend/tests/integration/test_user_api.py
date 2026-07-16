from __future__ import annotations

import pytest
from conftest import csrf_header, login
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import DocumentStatus
from app.db.models.content import Document
from app.db.models.identity import Feedback, SavedDocument, SearchHistory

pytestmark = pytest.mark.integration


async def active_document(db: AsyncSession) -> Document:
    document = await db.scalar(select(Document).where(Document.status == DocumentStatus.ACTIVE))
    assert document is not None
    return document


async def test_profile_preferences_and_stats(client: AsyncClient) -> None:
    await login(client)
    updated = await client.patch(
        "/api/users/me",
        json={
            "displayName": "Обновлённое имя",
            "email": "renamed@pyanswer.local",
            "preferences": {
                "defaultSearchMode": "vector",
                "defaultSearchView": "answer",
                "defaultPageSize": 20,
                "autoOpenScores": True,
                "confirmExternalNavigation": False,
            },
        },
        headers=csrf_header(client),
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["displayName"] == "Обновлённое имя"
    assert body["email"] == "renamed@pyanswer.local"
    assert body["preferences"]["defaultSearchMode"] == "vector"

    stats = await client.get("/api/users/me/stats")
    assert stats.status_code == 200
    assert stats.json() == {
        "documentSearches": 5,
        "ragSearches": 3,
        "savedDocuments": 3,
        "ratedAnswers": 1,
    }


async def test_profile_email_must_remain_unique(client: AsyncClient) -> None:
    await login(client)
    response = await client.patch(
        "/api/users/me",
        json={"email": "EDITOR@PYANSWER.LOCAL"},
        headers=csrf_header(client),
    )
    assert response.status_code == 409


async def test_history_is_private_paginated_and_deletable(
    client: AsyncClient, db: AsyncSession
) -> None:
    await login(client)
    own = await client.get("/api/history", params={"page": 1, "page_size": 3})
    assert own.status_code == 200
    body = own.json()
    assert len(body["items"]) == 3
    assert body["pagination"]["total"] == 8
    history_id = body["items"][0]["id"]

    removed = await client.delete(f"/api/history/{history_id}", headers=csrf_header(client))
    assert removed.status_code == 204
    assert await db.get(SearchHistory, history_id) is None

    cleared = await client.delete("/api/history", headers=csrf_header(client))
    assert cleared.status_code == 204
    remaining = await db.scalar(select(func.count()).select_from(SearchHistory))
    assert remaining == 0


async def test_user_cannot_delete_another_users_history(
    client: AsyncClient, db: AsyncSession
) -> None:
    foreign = await db.scalar(select(SearchHistory).limit(1))
    assert foreign is not None
    await login(client, "editor@pyanswer.local")
    response = await client.delete(f"/api/history/{foreign.id}", headers=csrf_header(client))
    assert response.status_code == 404


async def test_save_and_unsave_are_idempotent(client: AsyncClient, db: AsyncSession) -> None:
    editor = await login(client, "editor@pyanswer.local")
    document = await active_document(db)
    url = f"/api/saved/{document.id}"

    first = await client.post(url, headers=csrf_header(client))
    second = await client.post(url, headers=csrf_header(client))
    assert first.status_code == second.status_code == 200
    count = await db.scalar(
        select(func.count())
        .select_from(SavedDocument)
        .where(
            SavedDocument.user_id == editor["id"],
            SavedDocument.document_id == document.id,
        )
    )
    assert count == 1

    listed = await client.get("/api/saved")
    assert listed.status_code == 200
    assert listed.json()["pagination"]["total"] == 1

    assert (await client.delete(url, headers=csrf_header(client))).status_code == 204
    assert (await client.delete(url, headers=csrf_header(client))).status_code == 204
    assert (await client.get("/api/saved")).json()["pagination"]["total"] == 0


async def test_hidden_document_is_not_exposed_or_saved(
    client: AsyncClient, db: AsyncSession
) -> None:
    hidden = await db.scalar(select(Document).where(Document.status == DocumentStatus.HIDDEN))
    assert hidden is not None
    public = await client.get(f"/api/documents/{hidden.id}")
    assert public.status_code == 404

    await login(client)
    saved = await client.post(f"/api/saved/{hidden.id}", headers=csrf_header(client))
    assert saved.status_code == 404
    assert "hidden" not in saved.text.casefold()


async def test_feedback_upsert_validation_and_delete(client: AsyncClient, db: AsyncSession) -> None:
    await login(client, "editor@pyanswer.local")
    payload = {
        "responseId": "rag-response-42",
        "value": "negative",
        "reason": "incomplete",
        "question": "Как настроить asyncio?",
        "comment": "  Нужен пример  ",
    }
    created = await client.post("/api/feedback", json=payload, headers=csrf_header(client))
    assert created.status_code == 200
    feedback_id = created.json()["id"]
    assert created.json()["comment"] == "Нужен пример"

    changed = await client.post(
        "/api/feedback",
        json={**payload, "value": "positive", "reason": None, "comment": "   "},
        headers=csrf_header(client),
    )
    assert changed.status_code == 200
    assert changed.json()["id"] == feedback_id
    assert changed.json()["value"] == "positive"
    count = await db.scalar(
        select(func.count()).select_from(Feedback).where(Feedback.response_id == "rag-response-42")
    )
    assert count == 1

    invalid = await client.post(
        "/api/feedback",
        json={**payload, "reason": "unknown"},
        headers=csrf_header(client),
    )
    assert invalid.status_code == 422
    assert (
        await client.delete(f"/api/feedback/{feedback_id}", headers=csrf_header(client))
    ).status_code == 204


async def test_user_cannot_delete_foreign_feedback(client: AsyncClient, db: AsyncSession) -> None:
    foreign = await db.scalar(select(Feedback).limit(1))
    assert foreign is not None
    await login(client, "editor@pyanswer.local")
    response = await client.delete(f"/api/feedback/{foreign.id}", headers=csrf_header(client))
    assert response.status_code == 404
