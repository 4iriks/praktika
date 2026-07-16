from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Mapping

import httpx

from app.core.config import Settings
from app.integrations.embeddings.base import (
    EmbeddingBatch,
    EmbeddingHealth,
    EmbeddingProvider,
    EmbeddingProviderError,
)

TRANSIENT_STATUS_CODES = frozenset({429, 502, 503, 504})


class OllamaEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
        cancellation: asyncio.Event | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or httpx.AsyncClient(
            base_url=settings.ollama_base_url.rstrip("/"),
            timeout=settings.embedding_timeout_seconds,
            follow_redirects=False,
        )
        self._owns_client = client is None
        self._cancellation = cancellation

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._settings.embedding_model

    @property
    def dimensions(self) -> int:
        return self._settings.embedding_dimensions

    @property
    def configuration_hash(self) -> str:
        data = {
            "provider": self.provider_name,
            "model": self.model_name,
            "dimensions": self.dimensions,
            "documentPreprocessing": "contextual_text:v1",
            "queryInstruction": self._settings.embedding_query_instruction,
        }
        encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    async def embed_documents(self, texts: list[str]) -> EmbeddingBatch:
        return await self._embed(texts)

    async def embed_query(self, query: str) -> EmbeddingBatch:
        normalized = query.strip()
        if not normalized:
            raise EmbeddingProviderError("EMBEDDING_INPUT_INVALID", "Пустой поисковый запрос")
        instructed = self._settings.embedding_query_instruction.format(query=normalized)
        return await self._embed([instructed])

    async def health(self) -> EmbeddingHealth:
        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return EmbeddingHealth(
                online=False,
                model_installed=False,
                model=self.model_name,
                dimensions=self.dimensions,
                message=f"Ollama недоступен: {type(exc).__name__}",
            )
        model_names = {
            str(item.get("name", ""))
            for item in payload.get("models", [])
            if isinstance(item, Mapping)
        }
        installed = self.model_name in model_names or any(
            name.split(":", 1)[0] == self.model_name.split(":", 1)[0] for name in model_names
        )
        return EmbeddingHealth(
            online=True,
            model_installed=installed,
            model=self.model_name,
            dimensions=self.dimensions,
            message="Embedding model установлен" if installed else "Embedding model не загружен",
        )

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _embed(self, texts: list[str]) -> EmbeddingBatch:
        if not texts:
            raise EmbeddingProviderError("EMBEDDING_INPUT_INVALID", "Пустой batch embeddings")
        if len(texts) > self._settings.embedding_batch_size:
            raise EmbeddingProviderError(
                "EMBEDDING_BATCH_TOO_LARGE",
                f"Batch embeddings ограничен {self._settings.embedding_batch_size} элементами",
            )
        max_characters = self._settings.embedding_max_input_tokens * 4
        if any(not text.strip() or len(text) > max_characters for text in texts):
            raise EmbeddingProviderError(
                "EMBEDDING_INPUT_TOO_LARGE",
                "Текст embeddings пуст или превышает безопасный лимит",
            )
        response = await self._request_with_retry(
            {
                "model": self.model_name,
                "input": texts,
                "truncate": False,
                "dimensions": self.dimensions,
                "keep_alive": self._settings.embedding_keep_alive,
            }
        )
        try:
            payload = response.json()
            raw_vectors = payload["embeddings"]
            vectors = tuple(tuple(float(value) for value in vector) for vector in raw_vectors)
        except (ValueError, KeyError, TypeError) as exc:
            raise EmbeddingProviderError(
                "EMBEDDING_RESPONSE_INVALID", "Ollama вернул некорректные embeddings"
            ) from exc
        if len(vectors) != len(texts) or any(len(vector) != self.dimensions for vector in vectors):
            actual = len(vectors[0]) if vectors else 0
            raise EmbeddingProviderError(
                "EMBEDDING_DIMENSION_MISMATCH",
                f"Ожидалась размерность {self.dimensions}, получена {actual}",
            )
        return EmbeddingBatch(
            model=str(payload.get("model", self.model_name)),
            vectors=vectors,
            dimensions=self.dimensions,
            prompt_tokens=_optional_int(payload.get("prompt_eval_count")),
            total_duration_ns=_optional_int(payload.get("total_duration")),
        )

    async def _request_with_retry(self, payload: dict[str, object]) -> httpx.Response:
        attempts = self._settings.embedding_max_retries + 1
        for attempt in range(attempts):
            self._raise_if_cancelled()
            try:
                response = await self._client.post("/api/embed", json=payload)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt + 1 >= attempts:
                    raise EmbeddingProviderError(
                        "EMBEDDING_PROVIDER_UNAVAILABLE",
                        "Ollama embeddings недоступны",
                        retryable=True,
                    ) from exc
                await self._backoff(attempt)
                continue
            if response.status_code in TRANSIENT_STATUS_CODES:
                if attempt + 1 >= attempts:
                    raise EmbeddingProviderError(
                        "EMBEDDING_PROVIDER_UNAVAILABLE",
                        f"Ollama временно недоступен ({response.status_code})",
                        retryable=True,
                    )
                await self._backoff(attempt)
                continue
            if response.status_code == 404:
                raise EmbeddingProviderError(
                    "EMBEDDING_MODEL_MISSING",
                    f"Модель {self.model_name} не установлена",
                )
            if response.is_error:
                raise EmbeddingProviderError(
                    "EMBEDDING_PROVIDER_ERROR",
                    f"Ollama отклонил embeddings ({response.status_code})",
                )
            return response
        raise AssertionError("Недостижимый конец retry loop")

    async def _backoff(self, attempt: int) -> None:
        delay = min(8.0, 0.5 * (2**attempt))
        if self._cancellation is None:
            await asyncio.sleep(delay)
            return
        try:
            await asyncio.wait_for(self._cancellation.wait(), timeout=delay)
        except TimeoutError:
            return
        self._raise_if_cancelled()

    def _raise_if_cancelled(self) -> None:
        if self._cancellation is not None and self._cancellation.is_set():
            raise EmbeddingProviderError("EMBEDDING_CANCELLED", "Создание embeddings отменено")


def _optional_int(value: object) -> int | None:
    return value if type(value) is int else None
