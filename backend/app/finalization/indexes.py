from __future__ import annotations

from uuid import UUID

from qdrant_client import models
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.enums import (
    DeduplicationStatus,
    DocumentStatus,
    ProcessingStatus,
    SearchIndexEntryStatus,
    SearchIndexVersionStatus,
)
from app.db.models.content import Document, DocumentChunk
from app.db.models.operations import SearchIndexEntry, SearchIndexVersion
from app.finalization.reporting import CheckResult, ReportStatus
from app.integrations.qdrant import QdrantIndexClient, QdrantIndexError, index_schema_from_settings


async def index_consistency_checks(
    db: AsyncSession, qdrant: QdrantIndexClient, settings: Settings
) -> list[CheckResult]:
    health = await qdrant.health()
    if not health.online:
        return [
            CheckResult(
                "qdrant_ready",
                ReportStatus.FAIL,
                health.message,
                actual="OFFLINE",
                expected="ONLINE",
            )
        ]
    active = await db.scalar(
        select(SearchIndexVersion).where(
            SearchIndexVersion.status == SearchIndexVersionStatus.ACTIVE
        )
    )
    if active is None:
        return [
            CheckResult(
                "active_index",
                ReportStatus.FAIL,
                "В PostgreSQL отсутствует ACTIVE search index version",
                actual=None,
                expected="ACTIVE",
            )
        ]
    checks: list[CheckResult] = []
    alias_target = await qdrant.alias_target(settings.qdrant_alias)
    checks.append(
        CheckResult(
            "qdrant_alias",
            ReportStatus.PASSED if alias_target == active.collection_name else ReportStatus.FAIL,
            "Alias должен указывать на ACTIVE collection",
            actual=alias_target,
            expected=active.collection_name,
        )
    )
    try:
        await qdrant.validate_collection(
            active.collection_name, index_schema_from_settings(settings)
        )
    except QdrantIndexError as exc:
        checks.append(
            CheckResult("collection_schema", ReportStatus.FAIL, exc.safe_message, actual=exc.code)
        )
    else:
        checks.append(CheckResult("collection_schema", ReportStatus.PASSED, "Schema совпадает"))
    points = await qdrant.count(active.collection_name)
    entries = (
        await db.scalar(
            select(func.count())
            .select_from(SearchIndexEntry)
            .where(
                SearchIndexEntry.index_version_id == active.id,
                SearchIndexEntry.status == SearchIndexEntryStatus.INDEXED,
            )
        )
        or 0
    )
    eligible = (
        await db.scalar(
            select(func.count())
            .select_from(DocumentChunk)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                Document.processing_status == ProcessingStatus.CHUNKED,
                Document.status.in_([DocumentStatus.ACTIVE, DocumentStatus.OUTDATED]),
                Document.deduplication_status == DeduplicationStatus.UNIQUE,
                Document.processing_error.is_(None),
                DocumentChunk.document_version == Document.version,
                func.length(func.btrim(DocumentChunk.text)) > 0,
            )
        )
        or 0
    )
    checks.extend(
        [
            _equal("qdrant_point_count", points, int(eligible)),
            _equal("index_entry_count", int(entries), points),
            _equal("index_manifest_point_count", active.point_count, points),
        ]
    )
    for code, field, value in (
        ("hidden_points_absent", "document_status", DocumentStatus.HIDDEN),
        ("failed_points_absent", "processing_status", ProcessingStatus.FAILED),
        ("duplicate_points_absent", "deduplication_status", DeduplicationStatus.EXACT_DUPLICATE),
    ):
        count = await qdrant.count_filter(active.collection_name, _match(field, str(value)))
        checks.append(_equal(code, count, 0))
    samples = await qdrant.sample_payloads(active.collection_name, limit=100)
    stale = await _stale_samples(db, samples)
    checks.append(_equal("sample_payloads_current", stale, 0))
    return checks


def _match(field: str, value: str) -> models.Filter:
    return models.Filter(
        must=[models.FieldCondition(key=field, match=models.MatchValue(value=value))]
    )


async def _stale_samples(db: AsyncSession, samples: list[dict[str, object]]) -> int:
    stale = 0
    for payload in samples:
        raw_document_id = payload.get("document_id")
        raw_chunk_id = payload.get("chunk_id")
        raw_version = payload.get("document_version")
        try:
            document_id = UUID(str(raw_document_id))
            chunk_id = UUID(str(raw_chunk_id))
            version = int(str(raw_version))
        except (TypeError, ValueError):
            stale += 1
            continue
        row = (
            await db.execute(
                select(Document.version, DocumentChunk.document_version)
                .join(DocumentChunk, DocumentChunk.document_id == Document.id)
                .where(Document.id == document_id, DocumentChunk.id == chunk_id)
            )
        ).one_or_none()
        if row is None or row[0] != version or row[1] != version:
            stale += 1
    return stale


def _equal(code: str, actual: object, expected: object) -> CheckResult:
    return CheckResult(
        code,
        ReportStatus.PASSED if actual == expected else ReportStatus.FAIL,
        "Значения согласованы" if actual == expected else "Обнаружено рассогласование",
        actual=actual,
        expected=expected,
    )
