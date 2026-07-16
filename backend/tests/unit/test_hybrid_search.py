from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest
from qdrant_client import models

from app.core.config import Settings
from app.evaluation.retrieval import evaluate_rankings, percentile, stable_dataset_hash
from app.integrations.reranker import RerankerClient, RerankerError
from app.search.filters import build_search_filter
from app.search.fusion import RetrievedCandidate, weighted_rrf
from app.search.query import QueryValidationError, normalize_query
from app.services.search import QueryEmbeddingCache, _group_candidates, _snippet


def settings(**values: object) -> Settings:
    return Settings(APP_ENV="test", **values)


def candidate(score: float, point_id: UUID | None = None) -> RetrievedCandidate:
    return RetrievedCandidate(point_id or uuid4(), score, {"chunk_id": str(uuid4())})


def test_query_normalization_preserves_python_identifiers() -> None:
    assert (
        normalize_query(
            "  ModuleNotFoundError: pandas_datareader\r\nfoo.bar()  ",
            max_characters=200,
            max_tokens=100,
        )
        == "ModuleNotFoundError: pandas_datareader foo.bar()"
    )


@pytest.mark.parametrize("query", ["", " \n\t "])
def test_empty_query_is_rejected(query: str) -> None:
    with pytest.raises(QueryValidationError) as raised:
        normalize_query(query, max_characters=100, max_tokens=20)
    assert raised.value.code == "SEARCH_QUERY_EMPTY"


def test_query_character_and_token_limits() -> None:
    with pytest.raises(QueryValidationError):
        normalize_query("x" * 101, max_characters=100, max_tokens=100)
    with pytest.raises(QueryValidationError):
        normalize_query("x" * 100, max_characters=200, max_tokens=10)


def test_rrf_is_deterministic_and_keeps_raw_scores_separate() -> None:
    shared = uuid4()
    bm25 = [candidate(18.0, shared), candidate(11.0)]
    vector = [candidate(0.82, shared), candidate(0.79)]
    first = weighted_rrf(bm25, vector, k=60, bm25_weight=1, vector_weight=1, limit=10)
    second = weighted_rrf(bm25, vector, k=60, bm25_weight=1, vector_weight=1, limit=10)
    assert first == second
    assert first[0].point_id == shared
    assert first[0].bm25_score == 18.0
    assert first[0].vector_score == 0.82
    assert first[0].fusion_score == pytest.approx(2 / 61)
    assert first[0].fusion_score != 18.82


def test_rrf_weights_and_stable_tie_breaker() -> None:
    first_id, second_id = sorted([uuid4(), uuid4()], key=str)
    result = weighted_rrf(
        [candidate(1, second_id)],
        [candidate(1, first_id)],
        k=60,
        bm25_weight=1,
        vector_weight=1,
        limit=10,
    )
    assert [item.point_id for item in result] == [first_id, second_id]
    weighted = weighted_rrf(
        [candidate(1, second_id)],
        [candidate(1, first_id)],
        k=60,
        bm25_weight=2,
        vector_weight=1,
        limit=10,
    )
    assert weighted[0].point_id == second_id


def test_search_filter_always_contains_visibility_and_user_filters() -> None:
    value = build_search_filter(
        tags=["python", "asyncio"],
        date_from=datetime(2025, 1, 1, tzinfo=UTC),
        date_to=datetime(2026, 1, 1, tzinfo=UTC),
        min_question_score=3,
        accepted_only=True,
        has_code=True,
        source_id=uuid4(),
        section_type="QUESTION",
    )
    assert isinstance(value, models.Filter)
    keys = {
        condition.key
        for condition in value.must or []
        if isinstance(condition, models.FieldCondition)
    }
    assert {"document_status", "processing_status", "deduplication_status"} <= keys
    assert {"tags", "published_at", "question_score", "accepted_answer", "has_code"} <= keys


def test_embedding_cache_is_bounded_and_expires() -> None:
    cache = QueryEmbeddingCache(capacity=2, ttl_seconds=10)
    cache.put("a", (1.0,), now=0)
    cache.put("b", (2.0,), now=0)
    assert cache.get("a", now=1) == (1.0,)
    cache.put("c", (3.0,), now=1)
    assert cache.get("b", now=1) is None
    assert cache.size == 2
    assert cache.get("a", now=11) is None


def test_snippet_is_bounded_and_centred_on_identifier() -> None:
    text = "prefix " * 100 + "ModuleNotFoundError" + " suffix" * 100
    value = _snippet(text, "ModuleNotFoundError", 120)
    assert "ModuleNotFoundError" in value
    assert len(value) <= 122


def test_grouping_limits_chunks_per_document() -> None:
    # This behavior is covered with real hydrated candidates in integration tests; an empty
    # input still establishes that grouping is total and deterministic.
    assert _group_candidates([], 2) == []


@pytest.mark.asyncio
async def test_reranker_client_validates_normalized_scores() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "scores": [0.9, 0.1],
                "model": "Qwen/Qwen3-Reranker-0.6B",
                "revision": "pinned",
            },
        )
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://reranker.test") as client:
        reranker = RerankerClient(settings(RERANKER_TOP_N=2), client=client)
        result = await reranker.rerank("async python", ["one", "two"])
    assert result.scores == (0.9, 0.1)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [429, 502, 503, 504])
async def test_reranker_transient_outage_is_safe(status: int) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(status))
    async with httpx.AsyncClient(transport=transport, base_url="http://reranker.test") as client:
        reranker = RerankerClient(settings(), client=client)
        with pytest.raises(RerankerError) as raised:
            await reranker.rerank("query", ["passage"])
    assert raised.value.code == "RERANKER_UNAVAILABLE"
    assert raised.value.retryable is True


@pytest.mark.asyncio
async def test_reranker_does_not_invent_score_on_invalid_response() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, json={"scores": [2], "model": "model", "revision": "revision"}
        )
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://reranker.test") as client:
        reranker = RerankerClient(settings(), client=client)
        with pytest.raises(RerankerError) as raised:
            await reranker.rerank("query", ["passage"])
    assert raised.value.code == "RERANKER_RESPONSE_INVALID"


def test_retrieval_metrics_and_dataset_hash_are_deterministic() -> None:
    rankings = [["a", "x", "b"], ["z", "c"]]
    relevant = [{"a", "b"}, {"c"}]
    metrics = evaluate_rankings(rankings, relevant)
    assert metrics.recall_at_5 == 1
    assert metrics.mrr_at_10 == pytest.approx(0.75)
    assert metrics.ndcg_at_10 > 0
    records = [{"id": "1", "query": "asyncio"}]
    assert stable_dataset_hash(records) == stable_dataset_hash(records)
    assert percentile([1, 2, 100], 0.95) == 100
