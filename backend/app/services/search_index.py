from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.core.config import Settings
from app.core.enums import (
    AuditAction,
    AuditEntityType,
    AuditOutcome,
    DeduplicationStatus,
    DocumentStatus,
    IndexStatus,
    JobEventLevel,
    JobStage,
    JobType,
    ProcessingStatus,
    SearchIndexEntryStatus,
    SearchIndexVersionStatus,
)
from app.db.base import utc_now
from app.db.models.content import Document, DocumentChunk, DocumentTag
from app.db.models.identity import User
from app.db.models.operations import (
    AuditEvent,
    Job,
    SearchIndexEntry,
    SearchIndexVersion,
)
from app.db.repositories.jobs import add_job_event, update_job_progress
from app.integrations.embeddings import EmbeddingProvider, EmbeddingProviderError
from app.integrations.qdrant import (
    IndexPoint,
    IndexSchema,
    QdrantIndexClient,
    QdrantIndexError,
    SparseEmbeddingProvider,
    build_index_payload,
    stable_point_id,
)
from app.integrations.qdrant.schema import chunk_is_eligible
from app.integrations.qdrant.sparse import SparseProviderError
from app.services.content import document_statement, selected_tags
from app.workers.source_sync import HandlerOutcome


class SearchIndexServiceError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class PreparedPoint:
    entry: SearchIndexEntry
    point: IndexPoint


class SearchIndexJobHandler:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        schema: IndexSchema,
        embeddings: EmbeddingProvider,
        sparse: SparseEmbeddingProvider,
        qdrant: QdrantIndexClient,
        job_id: UUID,
        worker_id: UUID,
        shutdown_requested: asyncio.Event,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._schema = schema
        self._embeddings = embeddings
        self._sparse = sparse
        self._qdrant = qdrant
        self._job_id = job_id
        self._worker_id = worker_id
        self._shutdown_requested = shutdown_requested

    async def run(self) -> HandlerOutcome:
        try:
            job = await self._load_job()
            if job.type == JobType.DOCUMENT_REINDEX:
                return HandlerOutcome("COMPLETED", await self._document_reindex(job))
            if job.type == JobType.FULL_REINDEX:
                return HandlerOutcome("COMPLETED", await self._full_reindex(job))
            if job.type == JobType.SEARCH_INDEX_VALIDATE:
                return HandlerOutcome("COMPLETED", await self._validate(job))
            if job.type == JobType.SEARCH_INDEX_CLEANUP:
                return HandlerOutcome("COMPLETED", await self._cleanup(job))
            return HandlerOutcome(
                "FAILED",
                error_code="INDEX_JOB_TYPE_UNSUPPORTED",
                error_message="Indexer получил неподдерживаемый тип задания",
            )
        except SearchIndexServiceError as exc:
            return await self._error_outcome(exc)
        except (EmbeddingProviderError, QdrantIndexError, SparseProviderError) as exc:
            wrapped = SearchIndexServiceError(
                exc.code,
                exc.safe_message,
                retryable=getattr(exc, "retryable", False),
            )
            return await self._error_outcome(wrapped)
        except SQLAlchemyError:
            return await self._error_outcome(
                SearchIndexServiceError(
                    "INDEX_DATABASE_ERROR",
                    "Ошибка PostgreSQL при обновлении поискового индекса",
                    retryable=True,
                )
            )

    async def _load_job(self) -> Job:
        async with self._session_factory() as session:
            job = await session.get(Job, self._job_id)
            if job is None or job.claimed_by != self._worker_id:
                raise SearchIndexServiceError("INDEX_JOB_LOST", "Indexer больше не владеет job")
            return job

    async def _document_reindex(self, job: Job) -> dict[str, object]:
        if job.document_id is None:
            raise SearchIndexServiceError(
                "DOCUMENT_REINDEX_PAYLOAD_INVALID", "В задании отсутствует documentId"
            )
        await self._ensure_not_cancelled()
        async with self._session_factory() as session:
            active = await session.scalar(
                select(SearchIndexVersion).where(
                    SearchIndexVersion.status == SearchIndexVersionStatus.ACTIVE
                )
            )
            if active is None:
                raise SearchIndexServiceError(
                    "SEARCH_INDEX_NOT_INITIALIZED",
                    "Сначала выполните полную blue-green переиндексацию",
                )
            document = (
                await session.execute(document_statement().where(Document.id == job.document_id))
            ).scalar_one_or_none()
            if document is None:
                raise SearchIndexServiceError("DOCUMENT_NOT_FOUND", "Документ не найден")
            chunks = list(
                (
                    await session.scalars(
                        select(DocumentChunk)
                        .where(DocumentChunk.document_id == document.id)
                        .options(
                            selectinload(DocumentChunk.document).selectinload(Document.source),
                            selectinload(DocumentChunk.document)
                            .selectinload(Document.tag_links)
                            .selectinload(DocumentTag.tag),
                        )
                        .order_by(DocumentChunk.ordinal, DocumentChunk.id)
                    )
                ).all()
            )
            eligible = [
                chunk
                for chunk in chunks
                if chunk_is_eligible(
                    document,
                    chunk,
                    allow_possible_duplicates=self._settings.index_allow_possible_duplicates,
                )
            ]
            collection_name = active.collection_name
            active_id = active.id

        if await self._qdrant.alias_target(active.alias_name) != collection_name:
            raise SearchIndexServiceError(
                "INDEX_ALIAS_MISMATCH",
                "Активная версия PostgreSQL не совпадает с Qdrant alias",
                retryable=True,
            )

        await self._event(
            JobStage.EMBEDDING,
            "DOCUMENT_REINDEX_STARTED",
            "Начата переиндексация документа",
            {"documentId": job.document_id, "chunks": len(eligible)},
        )
        if not eligible:
            await self._qdrant.delete_document_points(collection_name, job.document_id)
            async with self._session_factory() as session, session.begin():
                await session.execute(
                    update(SearchIndexEntry)
                    .where(
                        SearchIndexEntry.index_version_id == active_id,
                        SearchIndexEntry.document_id == job.document_id,
                    )
                    .values(status=SearchIndexEntryStatus.REMOVED)
                )
                locked = await session.get(Document, job.document_id, with_for_update=True)
                if locked is not None:
                    locked.bm25_status = IndexStatus.NOT_INDEXED
                    locked.vector_status = IndexStatus.NOT_INDEXED
                    locked.last_indexed_at = None
                await self._add_worker_audit(
                    session,
                    job,
                    AuditAction.REINDEX_DOCUMENT,
                    AuditEntityType.DOCUMENT,
                    str(job.document_id),
                    "Документ исключён из поискового индекса",
                )
            return {"documentId": str(job.document_id), "points": 0, "eligible": False}

        prepared = await self._prepare_points(document, eligible, active_id)
        await self._ensure_not_cancelled()
        await self._qdrant.delete_document_points(collection_name, document.id)
        await self._qdrant.upsert(collection_name, [item.point for item in prepared])
        await self._ensure_not_cancelled()
        async with self._session_factory() as session, session.begin():
            locked = await session.get(Document, document.id, with_for_update=True)
            if locked is None:
                raise SearchIndexServiceError("DOCUMENT_NOT_FOUND", "Документ удалён")
            if locked.version != document.version or not chunk_is_eligible(
                locked,
                eligible[0],
                allow_possible_duplicates=self._settings.index_allow_possible_duplicates,
            ):
                raise SearchIndexServiceError(
                    "DOCUMENT_CHANGED_DURING_INDEX",
                    "Документ изменился во время индексации",
                    retryable=True,
                )
            await session.execute(
                update(SearchIndexEntry)
                .where(
                    SearchIndexEntry.index_version_id == active_id,
                    SearchIndexEntry.document_id == document.id,
                )
                .values(status=SearchIndexEntryStatus.REMOVED)
            )
            await self._store_entries(session, prepared)
            now = utc_now()
            locked.bm25_status = IndexStatus.READY
            locked.vector_status = IndexStatus.READY
            locked.last_indexed_at = now
            await self._add_worker_audit(
                session,
                job,
                AuditAction.REINDEX_DOCUMENT,
                AuditEntityType.DOCUMENT,
                str(document.id),
                "Документ проиндексирован в Qdrant",
            )
        return {
            "documentId": str(document.id),
            "points": len(prepared),
            "collection": collection_name,
            "indexVersionId": str(active_id),
        }

    async def _full_reindex(self, job: Job) -> dict[str, object]:
        version, snapshot_at = await self._prepare_full_version(job)
        await self._event(
            JobStage.PREPARING,
            "FULL_REINDEX_STARTED",
            "Создана blue-green версия поискового индекса",
            {"collection": version.collection_name, "schemaHash": version.schema_hash},
        )
        exists = version.collection_name in await self._qdrant.list_collections()
        if not exists:
            actual_server_version = await self._qdrant.server_version()
            if actual_server_version != self._settings.qdrant_server_version:
                raise SearchIndexServiceError(
                    "QDRANT_VERSION_MISMATCH",
                    "Версия Qdrant не совпадает с закреплённой конфигурацией",
                )
            probe = await self._embeddings.embed_documents(["Проверка размерности embeddings"])
            if probe.dimensions != self._schema.dense_dimensions:
                raise SearchIndexServiceError(
                    "EMBEDDING_DIMENSION_MISMATCH",
                    "Фактическая размерность embedding не совпадает со схемой индекса",
                )
            await self._qdrant.create_collection(version.collection_name, self._schema)
        await self._qdrant.validate_collection(version.collection_name, self._schema)

        total = await self._eligible_count(snapshot_at)
        async with self._session_factory() as session, session.begin():
            locked = await session.get(SearchIndexVersion, version.id, with_for_update=True)
            if locked is not None:
                locked.eligible_chunk_count = total
            await update_job_progress(
                session,
                job_id=self._job_id,
                worker_id=self._worker_id,
                total_items=total,
                stage=JobStage.EMBEDDING,
            )

        last_chunk_id = _checkpoint_uuid(job.checkpoint.get("lastChunkId"))
        processed = await self._indexed_entry_count(version.id)
        sample_vector: tuple[float, ...] | None = None
        while True:
            await self._ensure_not_cancelled()
            chunks = await self._load_eligible_batch(snapshot_at, last_chunk_id)
            if not chunks:
                break
            prepared = await self._prepare_points_for_mixed_documents(chunks, version.id)
            if prepared and sample_vector is None:
                sample_vector = prepared[0].point.dense
            await self._qdrant.upsert(version.collection_name, [item.point for item in prepared])
            await self._ensure_not_cancelled()
            processed += len(prepared)
            last_chunk_id = chunks[-1].id
            progress = min(95, round(processed / max(total, 1) * 95))
            async with self._session_factory() as session, session.begin():
                await self._store_entries(session, prepared)
                updated = await update_job_progress(
                    session,
                    job_id=self._job_id,
                    worker_id=self._worker_id,
                    progress=progress,
                    processed_items=processed,
                    total_items=total,
                    stage=JobStage.INDEXING_VECTOR,
                    checkpoint={
                        "indexVersionId": str(version.id),
                        "lastChunkId": str(last_chunk_id),
                        "snapshotAt": snapshot_at.isoformat(),
                        "processed": processed,
                    },
                )
                if updated is None:
                    raise SearchIndexServiceError(
                        "INDEX_JOB_LOST", "Indexer потерял lease во время full reindex"
                    )
            await self._event(
                JobStage.INDEXING_VECTOR,
                "INDEX_BATCH_COMMITTED",
                "Batch чанков записан в Qdrant",
                {"processed": processed, "total": total},
            )

        point_count = await self._qdrant.count(version.collection_name)
        if point_count != total or processed != total:
            raise SearchIndexServiceError(
                "INDEX_POINT_COUNT_MISMATCH",
                f"Ожидалось {total} points, записано {point_count}",
            )
        if point_count and sample_vector is not None:
            if await self._qdrant.sample_dense_query(version.collection_name, sample_vector) != 1:
                raise SearchIndexServiceError(
                    "INDEX_SAMPLE_VALIDATION_FAILED", "Проверочный dense query не вернул point"
                )
        await self._ensure_not_cancelled()
        async with self._session_factory() as session, session.begin():
            locked = await session.get(SearchIndexVersion, version.id, with_for_update=True)
            if locked is None:
                raise SearchIndexServiceError("INDEX_VERSION_LOST", "Версия индекса не найдена")
            locked.status = SearchIndexVersionStatus.READY
            locked.point_count = point_count
            locked.build_finished_at = utc_now()

        previous_alias_target = await self._qdrant.alias_target(version.alias_name)
        await self._qdrant.switch_alias(version.alias_name, version.collection_name)
        try:
            async with self._session_factory() as session, session.begin():
                locked = await session.get(SearchIndexVersion, version.id, with_for_update=True)
                if locked is None:
                    raise SearchIndexServiceError("INDEX_VERSION_LOST", "Версия индекса не найдена")
                now = utc_now()
                previous = list(
                    (
                        await session.scalars(
                            select(SearchIndexVersion)
                            .where(
                                SearchIndexVersion.status == SearchIndexVersionStatus.ACTIVE,
                                SearchIndexVersion.id != locked.id,
                            )
                            .with_for_update()
                        )
                    ).all()
                )
                for item in previous:
                    item.status = SearchIndexVersionStatus.RETIRED
                    item.retired_at = now
                locked.status = SearchIndexVersionStatus.ACTIVE
                locked.activated_at = now
                locked.failure_code = None
                locked.failure_message = None
                indexed_documents = select(SearchIndexEntry.document_id).where(
                    SearchIndexEntry.index_version_id == locked.id,
                    SearchIndexEntry.status == SearchIndexEntryStatus.INDEXED,
                )
                await session.execute(
                    update(Document)
                    .where(Document.id.in_(indexed_documents))
                    .values(
                        bm25_status=IndexStatus.READY,
                        vector_status=IndexStatus.READY,
                        last_indexed_at=now,
                    )
                )
                await self._add_worker_audit(
                    session,
                    job,
                    AuditAction.ACTIVATE_SEARCH_INDEX,
                    AuditEntityType.SEARCH_INDEX,
                    str(locked.id),
                    "Активирована новая blue-green версия поискового индекса",
                )
        except (SQLAlchemyError, SearchIndexServiceError):
            if previous_alias_target is not None:
                await self._qdrant.switch_alias(version.alias_name, previous_alias_target)
            else:
                await self._qdrant.remove_alias(version.alias_name)
            raise
        return {
            "indexVersionId": str(version.id),
            "collection": version.collection_name,
            "alias": version.alias_name,
            "points": point_count,
            "eligibleChunks": total,
            "schemaHash": version.schema_hash,
        }

    async def _validate(self, job: Job) -> dict[str, object]:
        version_id = _payload_uuid(job.payload.get("indexVersionId"))
        async with self._session_factory() as session:
            version = await session.get(SearchIndexVersion, version_id)
            if version is None:
                raise SearchIndexServiceError("INDEX_VERSION_NOT_FOUND", "Версия не найдена")
        await self._qdrant.validate_collection(version.collection_name, self._schema)
        points = await self._qdrant.count(version.collection_name)
        alias_target = await self._qdrant.alias_target(version.alias_name)
        if (
            version.status == SearchIndexVersionStatus.ACTIVE
            and alias_target != version.collection_name
        ):
            raise SearchIndexServiceError(
                "INDEX_ALIAS_MISMATCH", "Active version не совпадает с Qdrant alias"
            )
        async with self._session_factory() as session, session.begin():
            await self._add_worker_audit(
                session,
                job,
                AuditAction.VALIDATE_SEARCH_INDEX,
                AuditEntityType.SEARCH_INDEX,
                str(version.id),
                "Проверена схема поискового индекса",
            )
        return {
            "indexVersionId": str(version.id),
            "points": points,
            "aliasTarget": alias_target,
            "valid": True,
        }

    async def _cleanup(self, job: Job) -> dict[str, object]:
        dry_run = job.payload.get("dryRun") is not False
        confirm = job.payload.get("confirm") is True
        if not dry_run and not confirm:
            raise SearchIndexServiceError(
                "CLEANUP_CONFIRMATION_REQUIRED", "Удаление коллекций требует confirmation"
            )
        alias_target = await self._qdrant.alias_target(self._settings.qdrant_alias)
        qdrant_collections = await self._qdrant.list_collections()
        async with self._session_factory() as session:
            versions = list(
                (
                    await session.scalars(
                        select(SearchIndexVersion).order_by(
                            SearchIndexVersion.created_at.desc(), SearchIndexVersion.id.desc()
                        )
                    )
                ).all()
            )
        protected = {alias_target} if alias_target else set()
        retired_seen = 0
        candidates: list[str] = []
        threshold = utc_now() - timedelta(
            hours=self._settings.index_failed_collection_retention_hours
        )
        for version in versions:
            if version.status == SearchIndexVersionStatus.ACTIVE:
                protected.add(version.collection_name)
                continue
            if version.status == SearchIndexVersionStatus.RETIRED:
                retired_seen += 1
                if retired_seen <= self._settings.index_retain_retired_count:
                    protected.add(version.collection_name)
                    continue
            if version.status == SearchIndexVersionStatus.FAILED and version.created_at > threshold:
                protected.add(version.collection_name)
                continue
            if version.collection_name in qdrant_collections:
                candidates.append(version.collection_name)
        deleted: list[str] = []
        if not dry_run:
            for collection_name in candidates:
                if collection_name in protected:
                    continue
                await self._qdrant.delete_collection(collection_name)
                deleted.append(collection_name)
        async with self._session_factory() as session, session.begin():
            await self._add_worker_audit(
                session,
                job,
                AuditAction.CLEANUP_SEARCH_INDEX,
                AuditEntityType.SEARCH_INDEX,
                "search-index-cleanup",
                "Выполнена проверка устаревших Qdrant collections",
                metadata={"dryRun": dry_run, "candidates": candidates, "deleted": deleted},
            )
        return {"dryRun": dry_run, "candidates": candidates, "deleted": deleted}

    async def _prepare_full_version(self, job: Job) -> tuple[SearchIndexVersion, datetime]:
        payload_version = job.payload.get("indexVersionId")
        if payload_version is not None:
            version_id = _payload_uuid(payload_version)
            async with self._session_factory() as session:
                version = await session.get(SearchIndexVersion, version_id)
                if version is None:
                    raise SearchIndexServiceError(
                        "INDEX_VERSION_NOT_FOUND", "Build version из checkpoint не найдена"
                    )
                raw_snapshot = job.payload.get("snapshotAt")
                return version, _payload_datetime(raw_snapshot)
        now = utc_now()
        collection_name = (
            f"{self._settings.qdrant_collection_prefix}_{self._schema.hash[:12]}_"
            f"{now:%Y%m%d%H%M%S}_{str(job.id)[:8]}"
        )
        async with self._session_factory() as session, session.begin():
            locked_job = await session.get(Job, job.id, with_for_update=True)
            if locked_job is None or locked_job.claimed_by != self._worker_id:
                raise SearchIndexServiceError("INDEX_JOB_LOST", "Job потеряна")
            version = SearchIndexVersion(
                collection_name=collection_name,
                alias_name=self._settings.qdrant_alias,
                status=SearchIndexVersionStatus.BUILDING,
                schema_version=self._schema.schema_version,
                schema_hash=self._schema.hash,
                embedding_provider=self._embeddings.provider_name,
                embedding_model=self._embeddings.model_name,
                embedding_dimensions=self._embeddings.dimensions,
                embedding_instruction_hash=self._schema.query_instruction_hash,
                sparse_provider=self._sparse.provider_name,
                sparse_model=self._sparse.model_name,
                qdrant_server_version=self._settings.qdrant_server_version,
                qdrant_client_version=self._settings.qdrant_client_version,
                build_job_id=job.id,
                created_by=job.created_by,
                build_started_at=now,
                config={
                    "schemaHash": self._schema.hash,
                    "denseVector": "dense",
                    "sparseVector": "sparse",
                    "hnsw": {
                        "m": self._schema.hnsw_m,
                        "efConstruct": self._schema.hnsw_ef_construct,
                    },
                },
            )
            session.add(version)
            await session.flush()
            locked_job.payload = {
                **locked_job.payload,
                "indexVersionId": str(version.id),
                "snapshotAt": now.isoformat(),
            }
            return version, now

    async def _eligible_count(self, snapshot_at: datetime) -> int:
        async with self._session_factory() as session:
            return (
                await session.scalar(
                    select(func.count())
                    .select_from(DocumentChunk)
                    .join(Document, Document.id == DocumentChunk.document_id)
                    .where(*self._eligibility_filters(snapshot_at))
                )
                or 0
            )

    async def _indexed_entry_count(self, version_id: UUID) -> int:
        async with self._session_factory() as session:
            return (
                await session.scalar(
                    select(func.count())
                    .select_from(SearchIndexEntry)
                    .where(
                        SearchIndexEntry.index_version_id == version_id,
                        SearchIndexEntry.status == SearchIndexEntryStatus.INDEXED,
                    )
                )
                or 0
            )

    def _eligibility_filters(self, snapshot_at: datetime) -> tuple[ColumnElement[bool], ...]:
        dedup = [DeduplicationStatus.UNIQUE]
        if self._settings.index_allow_possible_duplicates:
            dedup.append(DeduplicationStatus.POSSIBLE_DUPLICATE)
        return (
            Document.updated_at <= snapshot_at,
            Document.processing_status == ProcessingStatus.CHUNKED,
            Document.status.in_([DocumentStatus.ACTIVE, DocumentStatus.OUTDATED]),
            Document.deduplication_status.in_(dedup),
            Document.processing_error.is_(None),
            DocumentChunk.document_version == Document.version,
            func.length(func.btrim(DocumentChunk.text)) > 0,
            func.length(func.btrim(DocumentChunk.contextual_text)) > 0,
        )

    async def _load_eligible_batch(
        self, snapshot_at: datetime, last_chunk_id: UUID | None
    ) -> list[DocumentChunk]:
        filters: list[ColumnElement[bool]] = list(self._eligibility_filters(snapshot_at))
        if last_chunk_id is not None:
            filters.append(DocumentChunk.id > last_chunk_id)
        batch_size = min(
            self._settings.index_embed_batch_size,
            self._settings.embedding_batch_size,
            self._settings.index_qdrant_upsert_batch_size,
        )
        async with self._session_factory() as session:
            return list(
                (
                    await session.scalars(
                        select(DocumentChunk)
                        .join(Document, Document.id == DocumentChunk.document_id)
                        .where(*filters)
                        .options(
                            selectinload(DocumentChunk.document).selectinload(Document.source),
                            selectinload(DocumentChunk.document)
                            .selectinload(Document.tag_links)
                            .selectinload(DocumentTag.tag),
                        )
                        .order_by(DocumentChunk.id)
                        .limit(batch_size)
                    )
                ).all()
            )

    async def _prepare_points(
        self,
        document: Document,
        chunks: list[DocumentChunk],
        index_version_id: UUID,
    ) -> list[PreparedPoint]:
        for chunk in chunks:
            chunk.document = document
        return await self._prepare_points_for_mixed_documents(chunks, index_version_id)

    async def _prepare_points_for_mixed_documents(
        self, chunks: list[DocumentChunk], index_version_id: UUID
    ) -> list[PreparedPoint]:
        texts = [chunk.contextual_text for chunk in chunks]
        dense_batch = await self._embeddings.embed_documents(texts)
        if dense_batch.dimensions != self._schema.dense_dimensions:
            raise SearchIndexServiceError(
                "EMBEDDING_DIMENSION_MISMATCH", "Embedding dimensions не совпадают со схемой"
            )
        sparse_vectors = self._sparse.embed_documents(texts)
        if len(sparse_vectors) != len(chunks):
            raise SearchIndexServiceError(
                "SPARSE_RESPONSE_INVALID", "Sparse provider вернул неверное число vectors"
            )
        now = utc_now()
        prepared: list[PreparedPoint] = []
        for chunk, dense, sparse in zip(chunks, dense_batch.vectors, sparse_vectors, strict=True):
            document = chunk.document
            point_id = stable_point_id(
                chunk.id,
                document.version,
                chunk.content_hash,
                self._schema.schema_version,
            )
            tags = [tag.normalized_name for tag in selected_tags(document)]
            prepared.append(
                PreparedPoint(
                    entry=SearchIndexEntry(
                        index_version_id=index_version_id,
                        chunk_id=chunk.id,
                        document_id=document.id,
                        document_version=document.version,
                        point_id=point_id,
                        chunk_content_hash=chunk.content_hash,
                        indexed_at=now,
                        status=SearchIndexEntryStatus.INDEXED,
                    ),
                    point=IndexPoint(
                        point_id=point_id,
                        dense=dense,
                        sparse=sparse,
                        payload=build_index_payload(
                            document,
                            chunk,
                            tags=tags,
                            indexed_at=now,
                            index_schema_version=self._schema.schema_version,
                        ),
                    ),
                )
            )
        return prepared

    async def _store_entries(self, session: AsyncSession, prepared: list[PreparedPoint]) -> None:
        if not prepared:
            return
        version_id = prepared[0].entry.index_version_id
        chunk_ids = [item.entry.chunk_id for item in prepared]
        existing = {
            item.chunk_id: item
            for item in (
                await session.scalars(
                    select(SearchIndexEntry)
                    .where(
                        SearchIndexEntry.index_version_id == version_id,
                        SearchIndexEntry.chunk_id.in_(chunk_ids),
                    )
                    .with_for_update()
                )
            ).all()
        }
        for item in prepared:
            record = existing.get(item.entry.chunk_id)
            if record is None:
                session.add(item.entry)
                continue
            record.document_version = item.entry.document_version
            record.point_id = item.entry.point_id
            record.chunk_content_hash = item.entry.chunk_content_hash
            record.indexed_at = item.entry.indexed_at
            record.status = SearchIndexEntryStatus.INDEXED
            record.failure_code = None
            record.failure_message = None
        await session.flush()

    async def _event(
        self,
        stage: JobStage,
        code: str,
        message: str,
        metrics: dict[str, object] | None = None,
    ) -> None:
        async with self._session_factory() as session, session.begin():
            await add_job_event(
                session,
                job_id=self._job_id,
                level=JobEventLevel.INFO,
                stage=stage,
                code=code,
                message=message,
                metrics=metrics,
            )

    async def _ensure_not_cancelled(self) -> None:
        if self._shutdown_requested.is_set():
            raise SearchIndexServiceError("INDEX_CANCELLED", "Indexer завершает работу")
        async with self._session_factory() as session:
            job = await session.get(Job, self._job_id)
            if job is None or job.claimed_by != self._worker_id:
                raise SearchIndexServiceError("INDEX_JOB_LOST", "Indexer потерял lease")
            if job.cancellation_requested_at is not None:
                raise SearchIndexServiceError("INDEX_CANCELLED", "Переиндексация отменена")

    async def _error_outcome(self, exc: SearchIndexServiceError) -> HandlerOutcome:
        job = await self._load_job()
        await self._mark_failure(job, exc)
        if exc.code == "INDEX_CANCELLED":
            return HandlerOutcome("CANCELLED", error_code=exc.code, error_message=exc.safe_message)
        if exc.retryable and job.attempt < job.max_attempts:
            return HandlerOutcome(
                "REQUEUED",
                error_code=exc.code,
                error_message=exc.safe_message,
                next_attempt_at=utc_now() + timedelta(seconds=min(300, 15 * 2**job.attempt)),
            )
        return HandlerOutcome("FAILED", error_code=exc.code, error_message=exc.safe_message)

    async def _mark_failure(self, job: Job, exc: SearchIndexServiceError) -> None:
        async with self._session_factory() as session, session.begin():
            cancelled = exc.code == "INDEX_CANCELLED"
            if job.document_id is not None and not cancelled:
                document = await session.get(Document, job.document_id, with_for_update=True)
                if document is not None:
                    failed_status = IndexStatus.OUTDATED if exc.retryable else IndexStatus.FAILED
                    document.bm25_status = failed_status
                    document.vector_status = failed_status
                    document.failure_reason = exc.safe_message
            if job.type == JobType.FULL_REINDEX and not cancelled:
                raw_version_id = job.payload.get("indexVersionId")
                if raw_version_id is not None:
                    version = await session.get(
                        SearchIndexVersion,
                        _payload_uuid(raw_version_id),
                        with_for_update=True,
                    )
                    if version is not None:
                        version.failure_code = exc.code
                        version.failure_message = exc.safe_message
                        if not exc.retryable or job.attempt >= job.max_attempts:
                            version.status = SearchIndexVersionStatus.FAILED
                            version.build_finished_at = utc_now()
            await add_job_event(
                session,
                job_id=job.id,
                level=JobEventLevel.WARNING if cancelled else JobEventLevel.ERROR,
                stage=job.stage,
                code=exc.code,
                message=exc.safe_message,
                metrics={"retryable": exc.retryable},
            )

    async def _add_worker_audit(
        self,
        session: AsyncSession,
        job: Job,
        action: AuditAction,
        entity_type: AuditEntityType,
        entity_id: str,
        summary: str,
        *,
        metadata: dict[str, object] | None = None,
    ) -> None:
        actor = await session.get(User, job.created_by) if job.created_by else None
        session.add(
            AuditEvent(
                actor_user_id=actor.id if actor else None,
                actor_name=actor.name if actor else "Indexer",
                actor_role=actor.role.code if actor else None,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                entity_label=entity_id,
                outcome=AuditOutcome.SUCCESS,
                ip_address=None,
                request_id=f"index-job:{job.id}",
                summary=summary,
                metadata_json=metadata or {"jobId": str(job.id)},
            )
        )
        await session.flush()


def _payload_uuid(value: object) -> UUID:
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise SearchIndexServiceError(
            "INDEX_PAYLOAD_INVALID", "Некорректный UUID в payload задания"
        ) from exc


def _checkpoint_uuid(value: object) -> UUID | None:
    if value is None:
        return None
    return _payload_uuid(value)


def _payload_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise SearchIndexServiceError("INDEX_PAYLOAD_INVALID", "В payload отсутствует snapshotAt")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SearchIndexServiceError("INDEX_PAYLOAD_INVALID", "Некорректный snapshotAt") from exc
    if parsed.tzinfo is None:
        raise SearchIndexServiceError("INDEX_PAYLOAD_INVALID", "snapshotAt должен быть UTC")
    return parsed
