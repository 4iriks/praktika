from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.core.config import Settings
from app.integrations.llm.base import (
    ChatMessage,
    LlmHealth,
    LlmProviderError,
    LlmResult,
    LlmStreamEvent,
)


class OllamaLlmProvider:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=settings.llm_base_url.rstrip("/"),
            timeout=httpx.Timeout(
                connect=min(15, settings.llm_timeout_seconds),
                read=settings.llm_timeout_seconds,
                write=30,
                pool=15,
            ),
            headers={"User-Agent": f"PyAnswer/{settings.app_version} local-rag"},
        )

    @property
    def model_name(self) -> str:
        return self._settings.llm_model

    async def health(self) -> LlmHealth:
        try:
            tags_response = await self._client.get("/api/tags")
            tags_response.raise_for_status()
            running_response = await self._client.get("/api/ps")
            running_response.raise_for_status()
            models = tags_response.json().get("models", [])
            running = running_response.json().get("models", [])
        except (httpx.HTTPError, ValueError, AttributeError):
            return LlmHealth(False, False, False, None, "Ollama недоступна")
        installed = next(
            (item for item in models if item.get("name") == self.model_name),
            None,
        )
        loaded = any(item.get("name") == self.model_name for item in running)
        digest = installed.get("digest") if isinstance(installed, dict) else None
        if installed is None:
            return LlmHealth(True, False, False, None, "LLM model не установлена")
        return LlmHealth(
            True,
            True,
            loaded,
            str(digest) if digest else None,
            "LLM model загружена" if loaded else "LLM model установлена, но не загружена",
        )

    async def stream_chat(self, messages: list[ChatMessage]) -> AsyncIterator[LlmStreamEvent]:
        if not messages or any(not item.content.strip() for item in messages):
            raise LlmProviderError("LLM_INPUT_INVALID", "Пустой prompt запрещён")
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": message.role, "content": message.content} for message in messages
            ],
            "stream": True,
            "think": False,
            "keep_alive": self._settings.llm_keep_alive,
            "options": {
                "num_ctx": self._settings.llm_num_ctx,
                "temperature": self._settings.llm_temperature,
                "top_p": self._settings.llm_top_p,
                "num_predict": self._settings.llm_max_output_tokens,
            },
        }
        emitted = 0
        try:
            async with self._client.stream("POST", "/api/chat", json=payload) as response:
                if response.status_code == 404:
                    raise LlmProviderError("LLM_MODEL_MISSING", "LLM model не установлена")
                if response.status_code >= 500:
                    raise LlmProviderError("LLM_UNAVAILABLE", "Ollama временно недоступна")
                if response.status_code >= 400:
                    raise LlmProviderError("LLM_REQUEST_REJECTED", "Ollama отклонила запрос")
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise LlmProviderError(
                            "LLM_STREAM_INVALID", "Ollama вернула некорректный stream"
                        ) from exc
                    if not isinstance(item, dict):
                        raise LlmProviderError(
                            "LLM_STREAM_INVALID", "Ollama вернула некорректный stream"
                        )
                    message = item.get("message")
                    content = message.get("content", "") if isinstance(message, dict) else ""
                    # The optional `thinking` field is deliberately ignored and never persisted.
                    if isinstance(content, str) and content:
                        emitted += len(content)
                        if emitted > self._settings.rag_max_answer_characters:
                            raise LlmProviderError(
                                "LLM_OUTPUT_TOO_LARGE", "Ответ локальной модели превышает лимит"
                            )
                        yield LlmStreamEvent(content=content, model=str(item.get("model") or ""))
                    if item.get("done") is True:
                        yield LlmStreamEvent(
                            done=True,
                            model=str(item.get("model") or self.model_name),
                            model_version=(
                                str(item["model_digest"]) if item.get("model_digest") else None
                            ),
                            prompt_tokens=_optional_int(item.get("prompt_eval_count")),
                            output_tokens=_optional_int(item.get("eval_count")),
                            total_duration_ns=_optional_int(item.get("total_duration")),
                        )
                        return
        except LlmProviderError:
            raise
        except httpx.TimeoutException as exc:
            raise LlmProviderError("LLM_TIMEOUT", "Истекло время ответа локальной модели") from exc
        except httpx.RequestError as exc:
            raise LlmProviderError("LLM_UNAVAILABLE", "Ollama недоступна") from exc
        raise LlmProviderError("LLM_STREAM_INCOMPLETE", "Ollama завершила stream без done")

    async def chat(self, messages: list[ChatMessage]) -> LlmResult:
        chunks: list[str] = []
        final: LlmStreamEvent | None = None
        async for event in self.stream_chat(messages):
            if event.content:
                chunks.append(event.content)
            if event.done:
                final = event
        if final is None:
            raise LlmProviderError("LLM_STREAM_INCOMPLETE", "Ollama не завершила ответ")
        return LlmResult(
            content="".join(chunks),
            model=final.model or self.model_name,
            model_version=final.model_version,
            prompt_tokens=final.prompt_tokens,
            output_tokens=final.output_tokens,
            total_duration_ns=final.total_duration_ns,
        )

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None
