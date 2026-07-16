from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class LlmStreamEvent:
    content: str = ""
    done: bool = False
    model: str | None = None
    model_version: str | None = None
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    total_duration_ns: int | None = None


@dataclass(frozen=True, slots=True)
class LlmResult:
    content: str
    model: str
    model_version: str | None
    prompt_tokens: int | None
    output_tokens: int | None
    total_duration_ns: int | None


@dataclass(frozen=True, slots=True)
class LlmHealth:
    online: bool
    model_installed: bool
    model_loaded: bool
    model_version: str | None
    message: str


class LlmProviderError(RuntimeError):
    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


class LlmProvider(Protocol):
    @property
    def model_name(self) -> str: ...

    def stream_chat(self, messages: list[ChatMessage]) -> AsyncIterator[LlmStreamEvent]: ...

    async def chat(self, messages: list[ChatMessage]) -> LlmResult: ...

    async def health(self) -> LlmHealth: ...

    async def close(self) -> None: ...
