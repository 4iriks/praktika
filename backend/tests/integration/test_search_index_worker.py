from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.enums import (
    DeduplicationStatus,
    DocumentStatus,
    IndexStatus,
    JobStage,
    JobStatus,
    JobType,
    ProcessingStatus,
    SearchIndexVersionStatus,
)
from app.db.base import utc_now
from app.db.models.content import Document
from app.db.models.identity import User
from app.db.models.operations import Job, SearchIndexVersion, WorkerInstance
from app.db.session import SessionFactory
from app.integrations.embeddings import EmbeddingBatch, EmbeddingHealth, EmbeddingProvider
from app.integrations.qdrant import IndexPoint, IndexSchema
from app.workers.indexer import IndexerRunner

pytestmark = pytest.mark.integration


class FakeEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dimensions: int) -> None:
        self._dimensions = dimensions
        self.document_inputs: list[str] = []

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return "qwen3-embedding:0.6b-test"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def configuration_hash(self) -> str:
        return "f" * 64

    async def embed_documents(self, texts: list[str]) -> EmbeddingBatch:
        self.document_inputs.extend(texts)
        vectors = tuple(
            tuple(1.0 if offset == 0 else 0.0 for offset in range(self._dimensions)) for _ in texts
        )
        return EmbeddingBatch(
            model=self.model_name,
            vectors=vectors,
            dimensions=self._dimensions,
        )

    async def embed_query(self, query: str) -> EmbeddingBatch:
        return await self.embed_documents([query])

    async def health(self) -> EmbeddingHealth:
        return EmbeddingHealth(True, True, self.model_name, self.dimensions, "ok")

    async def close(self) -> None:
        return None


class FakeQdrant:
    def __init__(self, server_version: str) -> None:
        self._server_version = server_version
        self.collections: dict[str, dict[UUID, IndexPoint]] = {}
        self.schemas: dict[str, IndexSchema] = {}
        self.aliases: dict[str, str] = {}

    async def list_collections(self) -> set[str]:
        return set(self.collections)

    async def server_version(self) -> str:
        return self._server_version

    async def create_collection(self, name: str, schema: IndexSchema) -> None:
        self.collections[name] = {}
        self.schemas[name] = schema

    async def validate_collection(self, name: str, schema: IndexSchema) -> None:
        assert name in self.collections
        assert self.schemas[name].hash == schema.hash

    async def upsert(self, name: str, points: list[IndexPoint]) -> None:
        self.collections[name].update({point.point_id: point for point in points})

    async def count(self, name: str) -> int:
        return len(self.collections[name])

    async def sample_dense_query(self, name: str, vector: tuple[float, ...]) -> int:
        assert len(vector) == self.schemas[name].dense_dimensions
        return min(1, len(self.collections[name]))

    async def alias_target(self, alias: str) -> str | None:
        return self.aliases.get(alias)

    async def switch_alias(self, alias: str, collection: str) -> None:
        assert collection in self.collections
        self.aliases[alias] = collection

    async def remove_alias(self, alias: str) -> None:
        self.aliases.pop(alias, None)

    async def delete_collection(self, name: str) -> None:
        self.collections.pop(name, None)
        self.schemas.pop(name, None)

    async def delete_document_points(self, name: str, document_id: UUID) -> None:
        self.collections[name] = {
            point_id: point
            for point_id, point in self.collections[name].items()
            if point.payload["document_id"] != str(document_id)
        }


async def _admin_id() -> UUID:
    async with SessionFactory() as session:
        value = await session.scalar(
            select(User.id).where(User.normalized_email == "admin@pyanswer.local")
        )
        assert value is not None
        return value


async def _queue_job(
    job_type: JobType,
    *,
    document_id: UUID | None = None,
    payload: dict[str, object] | None = None,
) -> UUID:
    async with SessionFactory() as session, session.begin():
        job = Job(
            type=job_type,
            status=JobStatus.QUEUED,
            stage=JobStage.PREPARING,
            document_id=document_id,
            created_by=await _admin_id(),
            payload=payload or {},
            cancellable=True,
            max_attempts=3,
        )
        session.add(job)
        await session.flush()
        return job.id


async def test_indexer_full_document_validate_cleanup_and_cancel() -> None:
    settings = get_settings()
    embeddings = FakeEmbeddingProvider(settings.embedding_dimensions)
    qdrant = FakeQdrant(settings.qdrant_server_version)

    async with SessionFactory() as session, session.begin():
        await session.execute(
            update(Job)
            .where(
                Job.type.in_(
                    [
                        JobType.DOCUMENT_REINDEX,
                        JobType.FULL_REINDEX,
                        JobType.SEARCH_INDEX_VALIDATE,
                        JobType.SEARCH_INDEX_CLEANUP,
                    ]
                ),
                Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            )
            .values(status=JobStatus.CANCELLED, finished_at=utc_now())
        )

    full_job_id = await _queue_job(JobType.FULL_REINDEX)
    runner = IndexerRunner(
        session_factory=SessionFactory,
        settings=settings,
        instance_id="stage6-test-indexer",
    )
    assert await runner.process_once(embeddings=embeddings, qdrant=qdrant) == full_job_id

    async with SessionFactory() as session:
        full_job = await session.get(Job, full_job_id)
        active = await session.scalar(
            select(SearchIndexVersion).where(
                SearchIndexVersion.status == SearchIndexVersionStatus.ACTIVE
            )
        )
        document = await session.scalar(
            select(Document)
            .where(
                Document.status == DocumentStatus.ACTIVE,
                Document.processing_status == ProcessingStatus.CHUNKED,
                Document.deduplication_status == DeduplicationStatus.UNIQUE,
            )
            .order_by(Document.id)
        )
        assert full_job is not None and full_job.status == JobStatus.COMPLETED
        assert active is not None and active.point_count > 0
        assert document is not None
        active_id = active.id
        collection_name = active.collection_name
        document_id = document.id
    assert qdrant.aliases[settings.qdrant_alias] == collection_name
    assert embeddings.document_inputs

    document_job_id = await _queue_job(JobType.DOCUMENT_REINDEX, document_id=document_id)
    assert await runner.process_once(embeddings=embeddings, qdrant=qdrant) == document_job_id
    async with SessionFactory() as session:
        document = await session.get(Document, document_id)
        assert document is not None
        assert document.bm25_status == IndexStatus.READY
        assert document.vector_status == IndexStatus.READY

    validate_job_id = await _queue_job(
        JobType.SEARCH_INDEX_VALIDATE,
        payload={"indexVersionId": str(active_id)},
    )
    assert await runner.process_once(embeddings=embeddings, qdrant=qdrant) == validate_job_id

    async with SessionFactory() as session, session.begin():
        old = SearchIndexVersion(
            collection_name="pyanswer_chunks_failed_old",
            alias_name=settings.qdrant_alias,
            status=SearchIndexVersionStatus.FAILED,
            schema_version="v0",
            schema_hash="0" * 64,
            embedding_provider="ollama",
            embedding_model="old",
            embedding_dimensions=settings.embedding_dimensions,
            embedding_instruction_hash="0" * 64,
            sparse_provider="qdrant_bm25",
            sparse_model="qdrant/bm25",
            qdrant_server_version=settings.qdrant_server_version,
            qdrant_client_version=settings.qdrant_client_version,
            created_at=utc_now() - timedelta(days=3),
            failure_code="TEST",
            failure_message="old failed build",
        )
        session.add(old)
    qdrant.collections[old.collection_name] = {}
    qdrant.schemas[old.collection_name] = qdrant.schemas[collection_name]

    cleanup_job_id = await _queue_job(
        JobType.SEARCH_INDEX_CLEANUP,
        payload={"dryRun": False, "confirm": True},
    )
    assert await runner.process_once(embeddings=embeddings, qdrant=qdrant) == cleanup_job_id
    assert old.collection_name not in qdrant.collections

    cancelled_job_id = await _queue_job(JobType.DOCUMENT_REINDEX, document_id=document_id)
    runner.request_shutdown()
    assert await runner.process_once(embeddings=embeddings, qdrant=qdrant) == cancelled_job_id
    await runner.close()

    async with SessionFactory() as session:
        cancelled_job = await session.get(Job, cancelled_job_id)
        document = await session.get(Document, document_id)
        worker = await session.scalar(
            select(WorkerInstance).where(WorkerInstance.instance_id == "stage6-test-indexer")
        )
        assert cancelled_job is not None and cancelled_job.status == JobStatus.CANCELLED
        assert document is not None and document.vector_status == IndexStatus.READY
        assert worker is not None and worker.status == "STOPPED"


async def test_indexer_dimension_mismatch_fails_without_alias_switch() -> None:
    settings = get_settings()
    embeddings = FakeEmbeddingProvider(settings.embedding_dimensions - 1)
    qdrant = FakeQdrant(settings.qdrant_server_version)
    async with SessionFactory() as session, session.begin():
        await session.execute(
            update(Job)
            .where(
                Job.type == JobType.DOCUMENT_REINDEX,
                Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            )
            .values(status=JobStatus.CANCELLED, finished_at=utc_now())
        )
    job_id = await _queue_job(JobType.FULL_REINDEX)
    runner = IndexerRunner(
        session_factory=SessionFactory,
        settings=settings,
        instance_id="stage6-dimension-test-indexer",
    )
    assert await runner.process_once(embeddings=embeddings, qdrant=qdrant) == job_id
    await runner.close()
    async with SessionFactory() as session:
        job = await session.get(Job, job_id)
        version = await session.scalar(
            select(SearchIndexVersion).where(SearchIndexVersion.build_job_id == job_id)
        )
        assert job is not None and job.status == JobStatus.FAILED
        assert job.error_code == "EMBEDDING_DIMENSION_MISMATCH"
        assert version is not None and version.status == SearchIndexVersionStatus.FAILED
    assert settings.qdrant_alias not in qdrant.aliases
