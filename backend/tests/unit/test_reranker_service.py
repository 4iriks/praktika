from __future__ import annotations

from collections.abc import Sequence

import httpx
import pytest

import app.reranker as service


class FakeModel:
    def __init__(self, values: Sequence[float] = (2.0, -2.0)) -> None:
        self.values = values
        self.received: list[tuple[str, str]] = []

    def predict(
        self, sentences: list[tuple[str, str]], *, batch_size: int, show_progress_bar: bool
    ) -> Sequence[float]:
        assert batch_size > 0 and show_progress_bar is False
        self.received = sentences
        return self.values[: len(sentences)]


@pytest.mark.asyncio
async def test_reranker_health_and_batch_scoring() -> None:
    model = FakeModel()
    service.runtime.model = model
    service.runtime.error = None
    transport = httpx.ASGITransport(app=service.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://reranker") as client:
        live = await client.get("/health/live")
        ready = await client.get("/health/ready")
        response = await client.post(
            "/rerank",
            json={
                "query": "asyncio",
                "passages": ["gather tasks", "dictionary merge"],
                "instruction": "Rank passage",
            },
        )
    assert live.status_code == ready.status_code == response.status_code == 200
    payload = response.json()
    assert 0 <= payload["scores"][0] <= 1
    assert payload["scores"][0] > payload["scores"][1]
    assert "Query: asyncio" in model.received[0][0]


@pytest.mark.asyncio
async def test_reranker_model_missing_is_honest() -> None:
    service.runtime.model = None
    service.runtime.error = "model missing"
    transport = httpx.ASGITransport(app=service.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://reranker") as client:
        ready = await client.get("/health/ready")
        response = await client.post(
            "/rerank",
            json={"query": "q", "passages": ["p"], "instruction": "rank"},
        )
    assert ready.status_code == response.status_code == 503
    assert "model missing" in ready.text


@pytest.mark.asyncio
async def test_reranker_rejects_excessive_batch() -> None:
    service.runtime.model = FakeModel([0.5] * 40)
    transport = httpx.ASGITransport(app=service.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://reranker") as client:
        response = await client.post(
            "/rerank",
            json={"query": "q", "passages": ["p"] * 31, "instruction": "rank"},
        )
    assert response.status_code == 422


def test_reranker_score_normalization_covers_logits_and_probabilities() -> None:
    assert service._normalized_score(0.5) == 0.5
    assert 0.99 < service._normalized_score(10) < 1
    assert 0 < service._normalized_score(-10) < 0.01
