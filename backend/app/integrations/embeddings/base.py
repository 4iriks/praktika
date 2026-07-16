from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class EmbeddingProviderError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class EmbeddingBatch:
    model: str
    vectors: tuple[tuple[float, ...], ...]
    dimensions: int
    prompt_tokens: int | None = None
    total_duration_ns: int | None = None


@dataclass(frozen=True, slots=True)
class EmbeddingHealth:
    online: bool
    model_installed: bool
    model: str
    dimensions: int
    message: str


class EmbeddingProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @property
    @abstractmethod
    def dimensions(self) -> int: ...

    @property
    @abstractmethod
    def configuration_hash(self) -> str: ...

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> EmbeddingBatch: ...

    @abstractmethod
    async def embed_query(self, query: str) -> EmbeddingBatch: ...

    @abstractmethod
    async def health(self) -> EmbeddingHealth: ...

    @abstractmethod
    async def close(self) -> None: ...
