from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from qdrant_client import models

from app.core.config import Settings
from app.core.enums import (
    DeduplicationStatus,
    DocumentStatus,
    ProcessingStatus,
)
from app.db.models.content import Document, DocumentChunk
from app.db.models.operations import Source
from app.integrations.embeddings import EmbeddingProviderError, OllamaEmbeddingProvider
from app.integrations.qdrant import (
    IndexPoint,
    QdrantIndexClient,
    QdrantIndexError,
    build_index_payload,
    index_schema_from_settings,
    sparse_provider_from_settings,
    stable_point_id,
)
from app.integrations.qdrant.client import PAYLOAD_INDEXES
from app.integrations.qdrant.schema import chunk_is_eligible


def settings(**values: object) -> Settings:
    return Settings(APP_ENV="test", **values)


def document_and_chunk() -> tuple[Document, DocumentChunk]:
    now = datetime.now(UTC)
    source = Source(
        name="Stack Overflow на русском",
        type="STACK_EXCHANGE",
        base_url="https://ru.stackoverflow.com",
        site="ru.stackoverflow",
        tag="python",
        enabled=True,
        status="IDLE",
        target_documents=5000,
        max_additional_answers=3,
        page_size=100,
    )
    source.id = uuid4()
    document = Document(
        source_id=source.id,
        external_id="1",
        source_url="https://ru.stackoverflow.com/questions/1",
        original_title="Python asyncio",
        normalized_title="Python asyncio",
        question_text="Как запустить coroutine?",
        author_name="Автор",
        published_at=now,
        score=10,
        views_count=20,
        answers_count=1,
        has_code=True,
        status=DocumentStatus.ACTIVE,
        content_hash="a" * 64,
        processing_status=ProcessingStatus.CHUNKED,
        deduplication_status=DeduplicationStatus.UNIQUE,
        version=2,
    )
    document.id = uuid4()
    document.source = source
    chunk = DocumentChunk(
        chunk_key="b" * 64,
        document_id=document.id,
        document_version=2,
        ordinal=0,
        section_type="QUESTION",
        text="await asyncio.gather(*tasks)",
        contextual_text="# Python asyncio\nawait asyncio.gather(*tasks)",
        content_hash="c" * 64,
        token_count=8,
        character_count=29,
        has_code=True,
        language="python",
    )
    chunk.id = uuid4()
    chunk.document = document
    return document, chunk


def test_schema_hash_is_deterministic_and_model_sensitive() -> None:
    first = index_schema_from_settings(settings())
    second = index_schema_from_settings(settings())
    changed = index_schema_from_settings(settings(EMBEDDING_MODEL="other:1"))
    compacted = index_schema_from_settings(settings(EMBEDDING_DOCUMENT_MAX_INPUT_TOKENS=64))
    assert first.hash == second.hash
    assert first.hash != changed.hash
    assert first.hash != compacted.hash


def test_point_id_is_stable_and_versioned() -> None:
    chunk_id = uuid4()
    first = stable_point_id(chunk_id, 1, "hash", "6.1")
    assert first == stable_point_id(chunk_id, 1, "hash", "6.1")
    assert first != stable_point_id(chunk_id, 2, "hash", "6.1")


@pytest.mark.parametrize(
    ("status", "processing", "dedup", "expected"),
    [
        (DocumentStatus.ACTIVE, ProcessingStatus.CHUNKED, DeduplicationStatus.UNIQUE, True),
        (DocumentStatus.HIDDEN, ProcessingStatus.CHUNKED, DeduplicationStatus.UNIQUE, False),
        (DocumentStatus.ACTIVE, ProcessingStatus.FAILED, DeduplicationStatus.UNIQUE, False),
        (
            DocumentStatus.ACTIVE,
            ProcessingStatus.CHUNKED,
            DeduplicationStatus.EXACT_DUPLICATE,
            False,
        ),
    ],
)
def test_chunk_eligibility(
    status: DocumentStatus,
    processing: ProcessingStatus,
    dedup: DeduplicationStatus,
    expected: bool,
) -> None:
    document, chunk = document_and_chunk()
    document.status = status
    document.processing_status = processing
    document.deduplication_status = dedup
    assert chunk_is_eligible(document, chunk) is expected


def test_payload_is_allowlisted_and_contains_no_credentials() -> None:
    document, chunk = document_and_chunk()
    payload = build_index_payload(
        document,
        chunk,
        tags=["python", "asyncio"],
        indexed_at=datetime.now(UTC),
        index_schema_version="6.1",
    )
    assert payload["document_id"] == str(document.id)
    serialized_keys = " ".join(payload).casefold()
    assert "password" not in serialized_keys
    assert "session" not in serialized_keys
    assert "token" not in serialized_keys
    assert "raw_html" not in serialized_keys


def test_native_bm25_is_explicit_and_fallback_does_not_activate() -> None:
    provider = sparse_provider_from_settings(settings())
    vector = provider.embed_documents(["asyncio gather Python"])[0]
    assert provider.provider_name == "qdrant_bm25"
    assert isinstance(vector, models.Document)
    assert vector.model == "qdrant/bm25"


@pytest.mark.asyncio
async def test_ollama_documents_have_no_query_instruction_and_query_has_it() -> None:
    received: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        received.append(payload["input"])
        return httpx.Response(200, json={"model": "test", "embeddings": [[0.0] * 4]})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    ) as client:
        provider = OllamaEmbeddingProvider(settings(EMBEDDING_DIMENSIONS=4), client=client)
        await provider.embed_documents(["document text"])
        await provider.embed_query("query text")
    assert received[0] == ["document text"]
    assert "Instruct:" in received[1][0] and "Query: query text" in received[1][0]


@pytest.mark.asyncio
async def test_ollama_compacts_only_document_input_deterministically() -> None:
    received: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        received.append(payload["input"])
        return httpx.Response(200, json={"model": "test", "embeddings": [[0.0] * 4]})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    ) as client:
        provider = OllamaEmbeddingProvider(
            settings(
                EMBEDDING_DIMENSIONS=4,
                EMBEDDING_DOCUMENT_MAX_INPUT_TOKENS=32,
            ),
            client=client,
        )
        document = "prefix " + "middle " * 80 + "suffix"
        await provider.embed_documents([document])
        first = received[-1][0]
        await provider.embed_documents([document])
        await provider.embed_query("query text")

    assert len(first) <= 32 * 4
    assert first == received[1][0]
    assert first.startswith("prefix") and first.endswith("suffix")
    assert "Instruct:" in received[2][0]


@pytest.mark.asyncio
async def test_embedding_dimension_mismatch_is_rejected() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"embeddings": [[0.0, 1.0]]})
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://ollama.test") as client:
        provider = OllamaEmbeddingProvider(settings(EMBEDDING_DIMENSIONS=4), client=client)
        with pytest.raises(EmbeddingProviderError) as raised:
            await provider.embed_documents(["document"])
    assert raised.value.code == "EMBEDDING_DIMENSION_MISMATCH"


class FakeAsyncQdrantClient:
    def __init__(self) -> None:
        self.aliases: dict[str, str] = {}
        self.collections = {"existing"}
        self.payload_indexes: list[str] = []
        self.upserted: list[models.PointStruct] = []
        self.deleted = False

    async def info(self) -> SimpleNamespace:
        return SimpleNamespace(version="1.18.2")

    async def collection_exists(self, name: str) -> bool:
        return name in self.collections

    async def create_collection(self, *, collection_name: str, **kwargs: object) -> bool:
        assert "vectors_config" in kwargs and "sparse_vectors_config" in kwargs
        self.collections.add(collection_name)
        return True

    async def create_payload_index(self, *, field_name: str, **kwargs: object) -> bool:
        assert kwargs["collection_name"] in self.collections
        self.payload_indexes.append(field_name)
        return True

    async def get_collection(self, name: str) -> SimpleNamespace:
        assert name in self.collections
        payload_schema = {field: {} for field, _ in PAYLOAD_INDEXES}
        value = {
            "config": {
                "params": {
                    "vectors": {"dense": {"size": 4}},
                    "sparse_vectors": {"sparse": {"modifier": "idf"}},
                }
            },
            "payload_schema": payload_schema,
        }
        return SimpleNamespace(model_dump=lambda **kwargs: value)

    async def upsert(self, *, points: list[models.PointStruct], **kwargs: object) -> bool:
        self.upserted.extend(points)
        return True

    async def delete(self, **kwargs: object) -> bool:
        self.deleted = True
        return True

    async def count(self, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(count=len(self.upserted))

    async def query_points(self, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(points=self.upserted[:1])

    async def get_aliases(self) -> SimpleNamespace:
        aliases = [
            SimpleNamespace(alias_name=alias, collection_name=collection)
            for alias, collection in self.aliases.items()
        ]
        return SimpleNamespace(aliases=aliases)

    async def update_collection_aliases(self, operations: list[object]) -> bool:
        for operation in operations:
            deleting = getattr(operation, "delete_alias", None)
            creating = getattr(operation, "create_alias", None)
            if deleting is not None:
                self.aliases.pop(deleting.alias_name, None)
            if creating is not None:
                self.aliases[creating.alias_name] = creating.collection_name
        return True

    async def get_collections(self) -> SimpleNamespace:
        return SimpleNamespace(
            collections=[SimpleNamespace(name=name) for name in sorted(self.collections)]
        )

    async def delete_collection(self, name: str) -> bool:
        self.collections.remove(name)
        return True


@pytest.mark.asyncio
async def test_qdrant_client_collection_points_alias_and_cleanup() -> None:
    fake = FakeAsyncQdrantClient()
    configuration = settings(EMBEDDING_DIMENSIONS=4)
    schema = index_schema_from_settings(configuration)
    client = QdrantIndexClient(configuration, client=fake)
    assert (await client.health()).online is True
    assert await client.server_version() == "1.18.2"

    await client.create_collection("green", schema)
    await client.validate_collection("green", schema)
    assert set(fake.payload_indexes) == {field for field, _ in PAYLOAD_INDEXES}

    document, chunk = document_and_chunk()
    point = IndexPoint(
        point_id=stable_point_id(chunk.id, 2, chunk.content_hash, schema.schema_version),
        dense=(1.0, 0.0, 0.0, 0.0),
        sparse=models.SparseVector(indices=[1], values=[1.0]),
        payload={"document_id": str(document.id)},
    )
    await client.upsert("green", [point])
    assert await client.count("green") == 1
    assert await client.sample_dense_query("green", point.dense) == 1
    await client.delete_document_points("green", document.id)
    assert fake.deleted is True

    assert await client.alias_target("pyanswer_chunks_current") is None
    await client.switch_alias("pyanswer_chunks_current", "green")
    assert await client.alias_target("pyanswer_chunks_current") == "green"
    await client.remove_alias("pyanswer_chunks_current")
    assert await client.alias_target("pyanswer_chunks_current") is None
    assert await client.list_collections() == {"existing", "green"}
    await client.delete_collection("existing")
    assert await client.list_collections() == {"green"}
    await client.close()


@pytest.mark.asyncio
async def test_qdrant_client_rejects_invalid_schema_and_large_batch() -> None:
    fake = FakeAsyncQdrantClient()
    configuration = settings(
        EMBEDDING_DIMENSIONS=4,
        EMBEDDING_BATCH_SIZE=1,
        INDEX_EMBED_BATCH_SIZE=1,
        INDEX_QDRANT_UPSERT_BATCH_SIZE=1,
    )
    client = QdrantIndexClient(configuration, client=fake)
    invalid = index_schema_from_settings(configuration)
    object.__setattr__(invalid, "dense_dimensions", 0)
    with pytest.raises(QdrantIndexError, match="Размерность"):
        await client.create_collection("invalid", invalid)

    document, _ = document_and_chunk()
    point = IndexPoint(
        point_id=uuid4(),
        dense=(0.0,) * 4,
        sparse=models.SparseVector(indices=[], values=[]),
        payload={"document_id": str(document.id)},
    )
    with pytest.raises(QdrantIndexError) as raised:
        await client.upsert("existing", [point, point])
    assert raised.value.code == "INDEX_BATCH_TOO_LARGE"

    cancellation = asyncio.Event()
    cancellation.set()
    cancelled = QdrantIndexClient(configuration, client=fake, cancellation=cancellation)
    with pytest.raises(QdrantIndexError) as raised:
        await cancelled.server_version()
    assert raised.value.code == "INDEX_CANCELLED"
