from __future__ import annotations

from collections.abc import AsyncIterator
from typing import ClassVar
from uuid import uuid4

import pytest
from conftest import csrf, csrf_header, login
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.rag as rag_service
import app.services.search as search_service
from app.db.models.content import Document, DocumentChunk
from app.db.models.identity import Feedback, SearchHistory
from app.db.models.operations import (
    RagResponse,
    RagResponseSource,
    SearchIndexVersion,
    SystemSetting,
)
from app.integrations.embeddings.base import EmbeddingBatch
from app.integrations.llm import ChatMessage, LlmHealth, LlmResult, LlmStreamEvent
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
        return RerankerResult(
            scores=tuple(0.92 - index * 0.02 for index in range(len(passages))),
            model="test-reranker",
            revision="test-revision",
        )

    async def close(self) -> None:
        return None


class FakeLlm:
    calls = 0
    model_name = "qwen3:8b"

    async def stream_chat(self, messages: list[ChatMessage]) -> AsyncIterator[LlmStreamEvent]:
        type(self).calls += 1
        assert messages[0].role == "system"
        assert "<<<CONTEXT>>>" in messages[1].content
        yield LlmStreamEvent(content="Используйте `asyncio.gather` ")
        yield LlmStreamEvent(content="для ожидания задач [1].")
        yield LlmStreamEvent(
            done=True,
            model=self.model_name,
            model_version="test-digest",
            prompt_tokens=120,
            output_tokens=12,
            total_duration_ns=1_000_000,
        )

    async def chat(self, messages: list[ChatMessage]) -> LlmResult:
        chunks: list[str] = []
        final: LlmStreamEvent | None = None
        async for event in self.stream_chat(messages):
            chunks.append(event.content)
            if event.done:
                final = event
        assert final is not None
        return LlmResult(
            content="".join(chunks),
            model=self.model_name,
            model_version=final.model_version,
            prompt_tokens=final.prompt_tokens,
            output_tokens=final.output_tokens,
            total_duration_ns=final.total_duration_ns,
        )

    async def health(self) -> LlmHealth:
        return LlmHealth(True, True, True, "test-digest", "ready")

    async def close(self) -> None:
        return None


async def prepare_search(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, *, empty: bool = False
) -> None:
    chunks = (
        await db.scalars(
            select(DocumentChunk)
            .join(Document)
            .where(Document.status == "ACTIVE", Document.processing_status == "CHUNKED")
            .order_by(DocumentChunk.id)
            .limit(3)
        )
    ).all()
    FakeQdrant.candidates = (
        []
        if empty
        else [
            RetrievedCandidate(
                point_id=uuid4(),
                score=10.0 - index,
                payload={"chunk_id": str(chunk.id)},
            )
            for index, chunk in enumerate(chunks)
        ]
    )
    db.add(
        SearchIndexVersion(
            collection_name="pyanswer_chunks_rag_test",
            alias_name="pyanswer_chunks_current",
            status="ACTIVE",
            schema_version="6.1",
            schema_hash="c" * 64,
            embedding_provider="ollama",
            embedding_model="qwen3-embedding:0.6b",
            embedding_dimensions=1024,
            embedding_instruction_hash="d" * 64,
            sparse_provider="qdrant_bm25",
            sparse_model="qdrant/bm25",
            qdrant_server_version="1.18.2",
            qdrant_client_version="1.18.0",
            point_count=len(FakeQdrant.candidates),
            eligible_chunk_count=len(FakeQdrant.candidates),
        )
    )
    await db.commit()
    monkeypatch.setattr(search_service, "OllamaEmbeddingProvider", lambda config: FakeEmbeddings())
    monkeypatch.setattr(search_service, "QdrantIndexClient", lambda config: FakeQdrant())
    monkeypatch.setattr(search_service, "RerankerClient", lambda config: FakeReranker())
    monkeypatch.setattr(rag_service, "OllamaLlmProvider", lambda config: FakeLlm())
    FakeLlm.calls = 0


async def test_non_stream_rag_persists_sources_history_and_feedback(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await prepare_search(db, monkeypatch)
    await login(client)
    payload = {
        "question": "Как ждать несколько asyncio задач?",
        "mode": "hybrid",
        "clientRequestId": "rag-idempotent-request",
    }
    first = await client.post("/api/ask", json=payload, headers=csrf_header(client))
    second = await client.post("/api/ask", json=payload, headers=csrf_header(client))
    assert first.status_code == second.status_code == 200, first.text
    response = first.json()
    assert response["answer"].endswith("[1].")
    assert response["citationValidationPassed"] is True
    assert response["confidenceLabel"] in {"MEDIUM", "HIGH"}
    assert response["sources"]
    assert response["model"] == "qwen3:8b"
    assert FakeLlm.calls == 1
    assert await db.scalar(select(func.count()).select_from(RagResponse)) == 1
    assert await db.scalar(select(func.count()).select_from(RagResponseSource)) >= 1
    assert (
        await db.scalar(
            select(func.count())
            .select_from(SearchHistory)
            .where(SearchHistory.view == "answer")
            .where(SearchHistory.request_id == "rag-idempotent-request")
        )
        == 1
    )
    feedback = await client.post(
        "/api/feedback",
        json={
            "responseId": response["responseId"],
            "value": "positive",
            "question": payload["question"],
        },
        headers=csrf_header(client),
    )
    assert feedback.status_code == 200, feedback.text
    saved_feedback = await db.scalar(
        select(Feedback).where(Feedback.response_id == response["responseId"])
    )
    assert saved_feedback is not None and saved_feedback.rag_response_id is not None
    missing = await client.post(
        "/api/feedback",
        json={
            "responseId": str(uuid4()),
            "value": "positive",
            "question": "missing",
        },
        headers=csrf_header(client),
    )
    assert missing.status_code == 404


async def test_stream_sends_sources_before_tokens_and_never_thinking(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await prepare_search(db, monkeypatch)
    await csrf(client)
    response = await client.post(
        "/api/ask/stream",
        json={
            "question": "asyncio gather",
            "mode": "hybrid",
            "clientRequestId": "rag-stream-request",
        },
        headers=csrf_header(client),
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert body.index("event: sources") < body.index("event: token")
    assert "event: done" in body
    assert "thinking" not in body.casefold()


async def test_insufficient_context_skips_llm_and_guest_policy_is_enforced(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await prepare_search(db, monkeypatch, empty=True)
    await csrf(client)
    insufficient = await client.post(
        "/api/ask",
        json={
            "question": "квантовая хромодинамика",
            "mode": "hybrid",
            "clientRequestId": "rag-insufficient-request",
        },
        headers=csrf_header(client),
    )
    assert insufficient.status_code == 200, insufficient.text
    assert insufficient.json()["insufficientContext"] is True
    assert insufficient.json()["generationTookMs"] == 0
    assert FakeLlm.calls == 0
    settings = await db.get(SystemSetting, 1)
    assert settings is not None
    settings.allow_guest_rag = False
    await db.commit()
    denied = await client.post(
        "/api/ask",
        json={
            "question": "python",
            "mode": "hybrid",
            "clientRequestId": "rag-guest-denied",
        },
        headers=csrf_header(client),
    )
    assert denied.status_code == 401


async def test_authenticated_stream_requires_csrf(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await prepare_search(db, monkeypatch)
    await login(client)
    response = await client.post(
        "/api/ask/stream",
        json={"question": "asyncio", "mode": "hybrid"},
    )
    assert response.status_code == 403


async def test_rag_diagnostics_are_admin_only_and_truthful(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await prepare_search(db, monkeypatch)
    await login(client)
    forbidden = await client.get("/api/admin/rag")
    assert forbidden.status_code == 403
    await login(client, "admin@pyanswer.local")
    response = await client.get("/api/admin/rag")
    assert response.status_code == 200, response.text
    assert response.json()["model"] == "qwen3:8b"
    assert response.json()["online"] is True
    assert response.json()["activeIndex"] == "c" * 64
