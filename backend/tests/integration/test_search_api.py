from __future__ import annotations

from typing import ClassVar
from uuid import uuid4

import pytest
from conftest import login
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.search as search_service
from app.db.models.content import DocumentChunk
from app.db.models.identity import SearchHistory
from app.db.models.operations import SearchIndexVersion, SearchRun
from app.integrations.embeddings.base import EmbeddingBatch
from app.integrations.reranker import RerankerResult
from app.search.fusion import RetrievedCandidate

pytestmark = pytest.mark.integration


class FakeEmbeddings:
    provider_name = "test"
    model_name = "test-embedding"
    dimensions = 4
    configuration_hash = "test-config"

    async def embed_query(self, query: str) -> EmbeddingBatch:
        return EmbeddingBatch(model=self.model_name, vectors=((0.1, 0.2, 0.3, 0.4),), dimensions=4)

    async def close(self) -> None:
        return None


class FakeQdrant:
    candidates: ClassVar[list[RetrievedCandidate]] = []

    async def query_sparse(self, *args: object, **kwargs: object) -> list[RetrievedCandidate]:
        return self.candidates

    async def query_dense(self, *args: object, **kwargs: object) -> list[RetrievedCandidate]:
        return list(reversed(self.candidates))

    async def close(self) -> None:
        return None


class FakeReranker:
    async def rerank(self, query: str, passages: list[str]) -> RerankerResult:
        count = len(passages)
        return RerankerResult(
            scores=tuple(0.9 - index / max(count, 1) / 10 for index in range(count)),
            model="Qwen/Qwen3-Reranker-0.6B",
            revision="pinned",
        )

    async def close(self) -> None:
        return None


def _version() -> SearchIndexVersion:
    return SearchIndexVersion(
        collection_name="pyanswer_chunks_test",
        alias_name="pyanswer_chunks_current",
        status="ACTIVE",
        schema_version="6.1",
        schema_hash="a" * 64,
        embedding_provider="ollama",
        embedding_model="qwen3-embedding:0.6b",
        embedding_dimensions=1024,
        embedding_instruction_hash="b" * 64,
        sparse_provider="qdrant_bm25",
        sparse_model="qdrant/bm25",
        qdrant_server_version="1.18.2",
        qdrant_client_version="1.18.0",
        point_count=3,
        eligible_chunk_count=3,
    )


async def _prepare(db: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    chunks = (await db.scalars(select(DocumentChunk).order_by(DocumentChunk.id).limit(3))).all()
    FakeQdrant.candidates = [
        RetrievedCandidate(
            point_id=uuid4(),
            score=10.0 - index,
            payload={"chunk_id": str(chunk.id)},
        )
        for index, chunk in enumerate(chunks)
    ]
    db.add(_version())
    await db.commit()
    monkeypatch.setattr(search_service, "OllamaEmbeddingProvider", lambda config: FakeEmbeddings())
    monkeypatch.setattr(search_service, "QdrantIndexClient", lambda config: FakeQdrant())
    monkeypatch.setattr(search_service, "RerankerClient", lambda config: FakeReranker())


async def test_real_hybrid_search_contract_and_idempotent_history(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _prepare(db, monkeypatch)
    await login(client)
    headers = {"X-Client-Request-ID": "same-browser-retry"}
    first = await client.get(
        "/api/search",
        params={"q": "asyncio gather", "mode": "hybrid", "page_size": 2},
        headers=headers,
    )
    second = await client.get(
        "/api/search",
        params={"q": "asyncio gather", "mode": "hybrid", "page_size": 2},
        headers=headers,
    )
    assert first.status_code == second.status_code == 200, first.text
    payload = first.json()
    assert payload["results"]
    assert payload["metrics"]["rerankerApplied"] is True
    assert payload["metrics"]["totalIsExact"] is False
    assert payload["results"][0]["indexVersion"] == "a" * 64
    assert payload["results"][0]["rerankerScore"] is not None
    assert await db.scalar(select(func.count()).select_from(SearchRun)) == 1
    assert (
        await db.scalar(
            select(func.count())
            .select_from(SearchHistory)
            .where(SearchHistory.request_id == "same-browser-retry")
        )
        == 1
    )


async def test_vector_mode_has_null_bm25_score(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _prepare(db, monkeypatch)
    response = await client.get("/api/search", params={"q": "контекст", "mode": "vector"})
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["bm25Score"] is None
    assert result["vectorScore"] is not None


async def test_deep_pagination_and_invalid_query_are_rejected(client: AsyncClient) -> None:
    deep = await client.get("/api/search", params={"q": "python", "page": 60, "page_size": 10})
    empty = await client.get("/api/search", params={"q": " "})
    assert deep.status_code == empty.status_code == 422
