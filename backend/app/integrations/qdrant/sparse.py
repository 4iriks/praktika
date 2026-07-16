from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from importlib import import_module
from typing import Protocol, cast

from qdrant_client import models

from app.core.config import Settings


class SparseProviderError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


type SparseRepresentation = models.Document | models.SparseVector


class SparseEmbeddingProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[SparseRepresentation]: ...


class QdrantBm25Provider(SparseEmbeddingProvider):
    def __init__(self, model: str) -> None:
        self._model = model

    @property
    def provider_name(self) -> str:
        return "qdrant_bm25"

    @property
    def model_name(self) -> str:
        return self._model

    def embed_documents(self, texts: list[str]) -> list[SparseRepresentation]:
        options = models.Bm25Config(language="russian", lowercase=True)
        return [models.Document(text=text, model=self._model, options=options) for text in texts]


class _SparseVectorLike(Protocol):
    indices: list[int]
    values: list[float]


class _FastEmbedModel(Protocol):
    def embed(self, documents: list[str]) -> Iterable[_SparseVectorLike]: ...


class FastEmbedBm25Provider(SparseEmbeddingProvider):
    def __init__(self, model: str) -> None:
        try:
            module = import_module("fastembed")
            model_type = cast(
                Callable[..., _FastEmbedModel], module.__dict__["SparseTextEmbedding"]
            )
            self._encoder = model_type(model_name=model)
        except (ImportError, AttributeError, TypeError) as exc:
            raise SparseProviderError(
                "SPARSE_PROVIDER_NOT_INSTALLED",
                "fastembed_bm25 выбран явно, но optional dependency fastembed не установлена",
            ) from exc
        self._model = model

    @property
    def provider_name(self) -> str:
        return "fastembed_bm25"

    @property
    def model_name(self) -> str:
        return self._model

    def embed_documents(self, texts: list[str]) -> list[SparseRepresentation]:
        raw_vectors = self._encoder.embed(texts)
        result: list[SparseRepresentation] = []
        try:
            for raw in raw_vectors:
                result.append(
                    models.SparseVector(
                        indices=[int(value) for value in raw.indices],
                        values=[float(value) for value in raw.values],
                    )
                )
        except (TypeError, AttributeError, ValueError) as exc:
            raise SparseProviderError(
                "SPARSE_EMBEDDING_FAILED", "fastembed вернул некорректный sparse vector"
            ) from exc
        return result


def sparse_provider_from_settings(settings: Settings) -> SparseEmbeddingProvider:
    if settings.sparse_provider == "qdrant_bm25":
        return QdrantBm25Provider(settings.sparse_model)
    if settings.sparse_provider == "fastembed_bm25":
        return FastEmbedBm25Provider(settings.sparse_model)
    raise SparseProviderError("SPARSE_PROVIDER_UNSUPPORTED", "Неизвестный sparse provider")
