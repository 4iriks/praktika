from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from app.core.enums import DeduplicationStatus, DocumentStatus, ProcessingStatus
from app.db.models.content import Answer, Document, DocumentChunk, DocumentRevision, Tag
from app.db.models.operations import IngestionFailure, Source, SourceSyncState
from app.finalization.reporting import generated_at, git_commit, tree_size


async def collect_corpus_manifest(
    db: AsyncSession,
    *,
    repo_root: Path,
    raw_archive: Path | None = None,
) -> dict[str, object]:
    source = await db.scalar(select(Source).order_by(Source.created_at).limit(1))
    sync_state = None
    if source is not None:
        sync_state = await db.get(SourceSyncState, source.id)
    status_counts = await _group_counts(db, Document.status)
    dedup_counts = await _group_counts(db, Document.deduplication_status)
    document_count = await _count(db, Document)
    real_document_filter = Document.external_id.not_like("stage4-%")
    real_document_count = (
        await db.scalar(select(func.count()).select_from(Document).where(real_document_filter)) or 0
    )
    real_processed_count = (
        await db.scalar(
            select(func.count())
            .select_from(Document)
            .where(real_document_filter, Document.processing_status == ProcessingStatus.CHUNKED)
        )
        or 0
    )
    active_count = status_counts.get(DocumentStatus.ACTIVE, 0)
    indexable = await db.scalar(
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
    first_date, last_date = (
        await db.execute(select(func.min(Document.published_at), func.max(Document.published_at)))
    ).one()
    database_bytes = await db.scalar(select(func.pg_database_size(func.current_database()))) or 0
    return {
        "generatedAt": generated_at(),
        "gitCommit": git_commit(repo_root),
        "source": {
            "name": source.name if source else None,
            "site": source.site if source else None,
            "tag": source.tag if source else None,
            "baseUrl": source.base_url if source else None,
        },
        "documents": document_count,
        "realDocuments": real_document_count,
        "realProcessedDocuments": real_processed_count,
        "activeDocuments": active_count,
        "hiddenDocuments": status_counts.get(DocumentStatus.HIDDEN, 0),
        "failedDocuments": status_counts.get(DocumentStatus.FAILED, 0),
        "duplicateDocuments": dedup_counts.get(DeduplicationStatus.EXACT_DUPLICATE, 0),
        "answers": await _count(db, Answer),
        "selectedAnswers": await db.scalar(
            select(func.count()).select_from(Answer).where(Answer.selected_for_corpus.is_(True))
        )
        or 0,
        "tags": await _count(db, Tag),
        "chunks": await _count(db, DocumentChunk),
        "revisions": await _count(db, DocumentRevision),
        "ingestionFailures": await _count(db, IngestionFailure),
        "firstDocumentDate": first_date,
        "lastDocumentDate": last_date,
        "lastSuccessfulSync": source.last_successful_sync_at if source else None,
        "initialSyncCompleted": bool(sync_state and sync_state.initial_sync_completed_at),
        "currentWatermark": sync_state.incremental_watermark if sync_state else None,
        "postgresqlSizeBytes": database_bytes,
        "rawArchiveSizeBytes": tree_size(raw_archive) if raw_archive else None,
        "indexableChunks": indexable or 0,
        "contentHashAggregate": await _content_hash_aggregate(db),
    }


async def _count(db: AsyncSession, model: type[object]) -> int:
    return await db.scalar(select(func.count()).select_from(model)) or 0


async def _group_counts(
    db: AsyncSession, column: ColumnElement[str] | InstrumentedAttribute[str]
) -> dict[str, int]:
    rows = (await db.execute(select(column, func.count()).group_by(column))).all()
    return {str(key): int(value) for key, value in rows}


async def _content_hash_aggregate(db: AsyncSession) -> str:
    digest = hashlib.sha256()
    hashes = await db.stream_scalars(select(Document.content_hash).order_by(Document.id))
    async for value in hashes:
        digest.update(value.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()
