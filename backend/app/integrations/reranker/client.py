from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import Settings


class RerankerError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class RerankerResult:
    scores: tuple[float, ...]
    model: str
    revision: str


@dataclass(frozen=True, slots=True)
class RerankerHealth:
    online: bool
    model_ready: bool
    message: str


class RerankerClient:
    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.AsyncClient(
            base_url=settings.reranker_base_url.rstrip("/"),
            timeout=settings.reranker_timeout_seconds,
            follow_redirects=False,
        )
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def health(self) -> RerankerHealth:
        try:
            live = await self._client.get("/health/live")
            if live.is_error:
                return RerankerHealth(False, False, "Reranker не отвечает")
            ready = await self._client.get("/health/ready")
        except (httpx.TimeoutException, httpx.NetworkError):
            return RerankerHealth(False, False, "Reranker недоступен")
        if ready.status_code == 200:
            return RerankerHealth(True, True, "Reranker model готова")
        return RerankerHealth(True, False, "Reranker online, model отсутствует")

    async def rerank(self, query: str, passages: list[str]) -> RerankerResult:
        if not passages or len(passages) > self._settings.reranker_top_n:
            raise RerankerError("RERANKER_INPUT_INVALID", "Некорректный batch reranker")
        try:
            response = await self._client.post(
                "/rerank",
                json={
                    "query": query,
                    "passages": passages,
                    "instruction": self._settings.reranker_instruction,
                },
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise RerankerError(
                "RERANKER_UNAVAILABLE", "Reranker недоступен", retryable=True
            ) from exc
        if response.status_code == 404:
            raise RerankerError("RERANKER_MODEL_MISSING", "Модель reranker не установлена")
        if response.status_code in {429, 502, 503, 504}:
            raise RerankerError(
                "RERANKER_UNAVAILABLE",
                f"Reranker временно недоступен ({response.status_code})",
                retryable=True,
            )
        if response.is_error:
            raise RerankerError(
                "RERANKER_FAILED", f"Reranker отклонил запрос ({response.status_code})"
            )
        try:
            payload = response.json()
            raw_scores = payload["scores"]
            scores = tuple(float(value) for value in raw_scores)
            model = str(payload["model"])
            revision = str(payload["revision"])
        except (ValueError, TypeError, KeyError) as exc:
            raise RerankerError("RERANKER_RESPONSE_INVALID", "Некорректный ответ reranker") from exc
        if len(scores) != len(passages) or any(score < 0 or score > 1 for score in scores):
            raise RerankerError("RERANKER_RESPONSE_INVALID", "Некорректные scores reranker")
        return RerankerResult(scores=scores, model=model, revision=revision)
