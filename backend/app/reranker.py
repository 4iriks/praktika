from __future__ import annotations

import asyncio
import math
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from importlib import import_module
from typing import Protocol, cast

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings


class CrossEncoderLike(Protocol):
    def predict(
        self, sentences: list[tuple[str, str]], *, batch_size: int, show_progress_bar: bool
    ) -> Sequence[float]: ...


class SentenceTransformersModule(Protocol):
    CrossEncoder: Callable[..., CrossEncoderLike]


class RerankRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=1000)
    passages: list[str] = Field(min_length=1, max_length=100)
    instruction: str = Field(min_length=1, max_length=1000)


class RerankResponse(BaseModel):
    scores: list[float]
    model: str
    revision: str


class Runtime:
    def __init__(self) -> None:
        self.model: CrossEncoderLike | None = None
        self.error: str | None = None
        self.semaphore = asyncio.Semaphore(get_settings().reranker_max_concurrent_requests)


runtime = Runtime()


def _load_model() -> CrossEncoderLike:
    settings = get_settings()
    module = cast(SentenceTransformersModule, import_module("sentence_transformers"))
    encoder_type = module.CrossEncoder
    return encoder_type(
        settings.reranker_model,
        revision=settings.reranker_model_revision,
        device=settings.reranker_device,
        local_files_only=True,
        max_length=settings.reranker_max_length,
        trust_remote_code=False,
    )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    try:
        runtime.model = await asyncio.to_thread(_load_model)
    except (ImportError, KeyError, OSError, ValueError, TypeError) as exc:
        runtime.error = f"{type(exc).__name__}: модель не подготовлена локально"
    yield
    runtime.model = None


app = FastAPI(title="PyAnswer Reranker", version="0.6.3", lifespan=lifespan)


@app.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "live"}


@app.get("/health/ready")
async def ready() -> dict[str, str]:
    if runtime.model is None:
        raise HTTPException(503, runtime.error or "Reranker model missing")
    return {"status": "ready", "model": get_settings().reranker_model}


@app.post("/rerank", response_model=RerankResponse)
async def rerank(payload: RerankRequest) -> RerankResponse:
    settings = get_settings()
    model = runtime.model
    if model is None:
        raise HTTPException(503, runtime.error or "Reranker model missing")
    if len(payload.passages) > settings.reranker_top_n:
        raise HTTPException(422, "Too many passages")
    try:
        await asyncio.wait_for(
            runtime.semaphore.acquire(), timeout=settings.reranker_queue_timeout_seconds
        )
    except TimeoutError as exc:
        raise HTTPException(503, "Reranker queue is saturated") from exc
    try:
        pairs = [
            (f"{payload.instruction}\nQuery: {payload.query}", passage)
            for passage in payload.passages
        ]
        raw = await asyncio.wait_for(
            asyncio.to_thread(
                model.predict,
                pairs,
                batch_size=settings.reranker_batch_size,
                show_progress_bar=False,
            ),
            timeout=settings.reranker_timeout_seconds,
        )
        scores = [_normalized_score(float(value)) for value in raw]
    except TimeoutError as exc:
        raise HTTPException(504, "Reranker timed out") from exc
    finally:
        runtime.semaphore.release()
    return RerankResponse(
        scores=scores,
        model=settings.reranker_model,
        revision=settings.reranker_model_revision,
    )


def _normalized_score(value: float) -> float:
    if 0 <= value <= 1:
        return value
    if value >= 0:
        exponent = math.exp(-min(value, 700))
        return 1 / (1 + exponent)
    exponent = math.exp(min(-value, 700))
    return 1 / (1 + exponent)
