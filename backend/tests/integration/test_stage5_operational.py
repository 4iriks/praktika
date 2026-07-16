from __future__ import annotations

import pytest
from conftest import login
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.content import Document, DocumentChunk, DocumentRevision
from app.db.models.operations import IngestionFailure, Job

pytestmark = pytest.mark.integration


async def add_operational_rows(db: AsyncSession) -> Document:
    async with db.begin():
        document = await db.scalar(select(Document).order_by(Document.id))
        job = await db.scalar(select(Job).order_by(Job.id))
        assert document is not None and job is not None
        revision = DocumentRevision(
            document_id=document.id,
            version=document.version,
            content_hash=document.content_hash[:64].ljust(64, "0"),
            metadata_hash="1" * 64,
            snapshot={"title": document.normalized_title},
            change_reason="TEST_IMPORT",
        )
        db.add(revision)
        db.add(
            DocumentChunk(
                chunk_key=f"test-{document.id}",
                document_id=document.id,
                document_version=document.version,
                ordinal=0,
                section_type="QUESTION",
                text="Очищенный тестовый текст",
                contextual_text="Заголовок\nОчищенный тестовый текст",
                content_hash="2" * 64,
                token_count=8,
                character_count=25,
                has_code=False,
            )
        )
        db.add(
            IngestionFailure(
                job_id=job.id,
                source_id=document.source_id,
                document_id=document.id,
                external_id=document.external_id,
                entity_type="QUESTION",
                error_code="SAFE_TEST_FAILURE",
                safe_message="Безопасная диагностическая ошибка",
                retryable=True,
                attempt=1,
                context={"password": "removed", "stage": "PROCESSING"},
            )
        )
    return document


async def test_editor_document_operational_endpoints_are_read_only_and_protected(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    document = await add_operational_rows(db)
    await login(client, "editor@pyanswer.local")
    for suffix in ("chunks", "revisions", "failures"):
        response = await client.get(f"/api/editor/documents/{document.id}/{suffix}")
        assert response.status_code == 200
        assert response.json()["pagination"]["total"] == 1
    failure_payload = (await client.get(f"/api/editor/documents/{document.id}/failures")).json()
    assert "password" not in str(failure_payload).casefold()

    await client.post("/api/auth/logout", headers={"X-CSRF-Token": client.cookies["pyanswer_csrf"]})
    await login(client, "user@pyanswer.local")
    denied = await client.get(f"/api/editor/documents/{document.id}/chunks")
    assert denied.status_code == 403


async def test_system_reports_real_ingestion_counts_and_future_services_offline(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await add_operational_rows(db)
    await login(client, "admin@pyanswer.local")
    response = await client.get("/api/admin/system")
    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics"]["answersCount"] > 0
    assert payload["metrics"]["chunksCount"] == 1
    assert payload["metrics"]["revisionsCount"] == 1
    assert payload["metrics"]["failuresCount"] == 1
    services = {item["id"]: item["status"] for item in payload["services"]}
    for name in ("qdrant", "ollama", "indexer", "bm25", "vector", "embedding", "reranker"):
        assert services[name] == "OFFLINE"


async def test_openapi_contains_stage5_operational_routes(client: AsyncClient) -> None:
    paths = (await client.get("/api/openapi.json")).json()["paths"]
    assert "/api/editor/documents/{document_id}/chunks" in paths
    assert "/api/editor/documents/{document_id}/revisions" in paths
    assert "/api/editor/documents/{document_id}/failures" in paths
    assert "/api/admin/ingestion/stats" in paths
