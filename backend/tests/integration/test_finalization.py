from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models.content import Document, DocumentChunk
from app.finalization.consistency import data_consistency_checks
from app.finalization.corpus import collect_corpus_manifest
from app.finalization.indexes import _stale_samples, index_consistency_checks
from app.finalization.reporting import ReportStatus
from app.integrations.qdrant import QdrantIndexClient

pytestmark = pytest.mark.integration


async def test_corpus_manifest_and_data_consistency(db: AsyncSession, tmp_path: Path) -> None:
    manifest = await collect_corpus_manifest(db, repo_root=tmp_path)
    checks = await data_consistency_checks(db)

    assert int(manifest["documents"]) >= 1
    assert int(manifest["chunks"]) >= 1
    assert manifest["contentHashAggregate"]
    assert {check.code for check in checks} >= {
        "document_identity_unique",
        "chunks_non_empty",
        "audit_credentials_absent",
        "corpus_has_chunks",
    }
    assert all(isinstance(check.status, ReportStatus) for check in checks)


async def test_index_consistency_reports_offline_and_missing_active(db: AsyncSession) -> None:
    offline = SimpleNamespace(
        health=lambda: None,
    )

    async def offline_health() -> SimpleNamespace:
        return SimpleNamespace(online=False, message="offline")

    offline.health = offline_health
    checks = await index_consistency_checks(
        db,
        cast(QdrantIndexClient, cast(Any, offline)),
        Settings(APP_ENV="test"),
    )
    assert checks[0].code == "qdrant_ready"
    assert checks[0].status == ReportStatus.FAIL

    online = SimpleNamespace()

    async def online_health() -> SimpleNamespace:
        return SimpleNamespace(online=True, message="online")

    online.health = online_health
    checks = await index_consistency_checks(
        db,
        cast(QdrantIndexClient, cast(Any, online)),
        Settings(APP_ENV="test"),
    )
    assert checks[0].code == "active_index"


async def test_stale_payload_detection(db: AsyncSession) -> None:
    document = await db.scalar(select(Document).order_by(Document.id).limit(1))
    assert document is not None
    chunk = await db.scalar(
        select(DocumentChunk).where(DocumentChunk.document_id == document.id).limit(1)
    )
    assert chunk is not None
    samples: list[dict[str, object]] = [
        {
            "document_id": str(document.id),
            "chunk_id": str(chunk.id),
            "document_version": document.version,
        },
        {"document_id": "bad", "chunk_id": "bad", "document_version": "bad"},
        {
            "document_id": str(uuid4()),
            "chunk_id": str(uuid4()),
            "document_version": 1,
        },
    ]
    assert await _stale_samples(db, samples) == 2
