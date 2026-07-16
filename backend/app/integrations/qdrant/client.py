from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from typing import TypeVar
from uuid import UUID

import httpx
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from app.core.config import Settings
from app.integrations.qdrant.schema import (
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    IndexPoint,
    IndexSchema,
)

T = TypeVar("T")


class QdrantIndexError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class QdrantHealth:
    online: bool
    version: str | None
    message: str


PAYLOAD_INDEXES: tuple[tuple[str, models.PayloadSchemaType], ...] = (
    ("document_id", models.PayloadSchemaType.KEYWORD),
    ("source_id", models.PayloadSchemaType.KEYWORD),
    ("tags", models.PayloadSchemaType.KEYWORD),
    ("published_at", models.PayloadSchemaType.DATETIME),
    ("question_score", models.PayloadSchemaType.INTEGER),
    ("accepted_answer", models.PayloadSchemaType.BOOL),
    ("has_code", models.PayloadSchemaType.BOOL),
    ("section_type", models.PayloadSchemaType.KEYWORD),
    ("document_status", models.PayloadSchemaType.KEYWORD),
    ("processing_status", models.PayloadSchemaType.KEYWORD),
    ("deduplication_status", models.PayloadSchemaType.KEYWORD),
    ("document_version", models.PayloadSchemaType.INTEGER),
)


class QdrantIndexClient:
    def __init__(
        self,
        settings: Settings,
        *,
        client: AsyncQdrantClient | None = None,
        cancellation: asyncio.Event | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or AsyncQdrantClient(
            url=settings.qdrant_url,
            timeout=round(settings.qdrant_timeout_seconds),
            prefer_grpc=False,
        )
        self._owns_client = client is None
        self._cancellation = cancellation

    async def close(self) -> None:
        if self._owns_client:
            await self._client.close()

    async def health(self) -> QdrantHealth:
        try:
            info = await self._run(self._client.info)
        except QdrantIndexError as exc:
            return QdrantHealth(False, None, exc.safe_message)
        return QdrantHealth(True, info.version, "Qdrant отвечает")

    async def server_version(self) -> str:
        info = await self._run(self._client.info)
        return info.version

    async def create_collection(self, collection_name: str, schema: IndexSchema) -> None:
        if schema.dense_dimensions <= 0:
            raise QdrantIndexError("INDEX_SCHEMA_INVALID", "Размерность dense vector некорректна")
        exists = await self._run(lambda: self._client.collection_exists(collection_name))
        if exists:
            raise QdrantIndexError("COLLECTION_EXISTS", "Физическая коллекция уже существует")
        await self._run(
            lambda: self._client.create_collection(
                collection_name=collection_name,
                vectors_config={
                    DENSE_VECTOR_NAME: models.VectorParams(
                        size=schema.dense_dimensions,
                        distance=models.Distance.COSINE,
                        hnsw_config=models.HnswConfigDiff(
                            m=schema.hnsw_m,
                            ef_construct=schema.hnsw_ef_construct,
                        ),
                    )
                },
                sparse_vectors_config={
                    SPARSE_VECTOR_NAME: models.SparseVectorParams(
                        index=models.SparseIndexParams(on_disk=False),
                        modifier=models.Modifier.IDF,
                    )
                },
                on_disk_payload=True,
                timeout=round(self._settings.index_request_timeout_seconds),
            )
        )
        for field_name, field_schema in PAYLOAD_INDEXES:
            await self._run(
                partial(
                    self._client.create_payload_index,
                    collection_name=collection_name,
                    field_name=field_name,
                    field_schema=field_schema,
                    wait=True,
                    timeout=round(self._settings.index_request_timeout_seconds),
                )
            )

    async def validate_collection(self, collection_name: str, schema: IndexSchema) -> None:
        info = await self._run(lambda: self._client.get_collection(collection_name))
        dumped = info.model_dump(mode="json")
        params = _mapping_at(dumped, "config", "params")
        vectors = params.get("vectors")
        sparse_vectors = params.get("sparse_vectors")
        if not isinstance(vectors, Mapping) or DENSE_VECTOR_NAME not in vectors:
            raise QdrantIndexError("INDEX_SCHEMA_MISMATCH", "Dense vector отсутствует")
        dense = vectors[DENSE_VECTOR_NAME]
        if not isinstance(dense, Mapping) or dense.get("size") != schema.dense_dimensions:
            raise QdrantIndexError(
                "INDEX_SCHEMA_MISMATCH", "Размерность dense collection не совпадает"
            )
        if not isinstance(sparse_vectors, Mapping) or SPARSE_VECTOR_NAME not in sparse_vectors:
            raise QdrantIndexError("INDEX_SCHEMA_MISMATCH", "Sparse vector отсутствует")
        payload_schema = dumped.get("payload_schema")
        if not isinstance(payload_schema, Mapping):
            raise QdrantIndexError("INDEX_SCHEMA_MISMATCH", "Payload indexes отсутствуют")
        missing = [field for field, _ in PAYLOAD_INDEXES if field not in payload_schema]
        if missing:
            raise QdrantIndexError(
                "INDEX_SCHEMA_MISMATCH",
                f"Отсутствуют payload indexes: {', '.join(missing)}",
            )

    async def upsert(self, collection_name: str, points: Sequence[IndexPoint]) -> None:
        if not points:
            return
        if len(points) > self._settings.index_qdrant_upsert_batch_size:
            raise QdrantIndexError(
                "INDEX_BATCH_TOO_LARGE",
                "Batch Qdrant превышает настроенный безопасный лимит",
            )
        await self._run(
            lambda: self._client.upsert(
                collection_name=collection_name,
                points=[point.to_qdrant() for point in points],
                wait=True,
                timeout=round(self._settings.index_request_timeout_seconds),
            )
        )

    async def delete_document_points(self, collection_name: str, document_id: UUID) -> None:
        selector = models.Filter(
            must=[
                models.FieldCondition(
                    key="document_id", match=models.MatchValue(value=str(document_id))
                )
            ]
        )
        await self._run(
            lambda: self._client.delete(
                collection_name=collection_name,
                points_selector=models.FilterSelector(filter=selector),
                wait=True,
                timeout=round(self._settings.index_request_timeout_seconds),
            )
        )

    async def count(self, collection_name: str) -> int:
        result = await self._run(
            lambda: self._client.count(collection_name=collection_name, exact=True)
        )
        return result.count

    async def sample_dense_query(self, collection_name: str, vector: Sequence[float]) -> int:
        response = await self._run(
            lambda: self._client.query_points(
                collection_name=collection_name,
                query=list(vector),
                using=DENSE_VECTOR_NAME,
                limit=1,
                with_payload=False,
                with_vectors=False,
            )
        )
        return len(response.points)

    async def alias_target(self, alias_name: str) -> str | None:
        response = await self._run(self._client.get_aliases)
        for item in response.aliases:
            if item.alias_name == alias_name:
                return item.collection_name
        return None

    async def switch_alias(self, alias_name: str, collection_name: str) -> None:
        current = await self.alias_target(alias_name)
        operations: list[models.CreateAliasOperation | models.DeleteAliasOperation] = []
        if current is not None:
            operations.append(
                models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=alias_name))
            )
        operations.append(
            models.CreateAliasOperation(
                create_alias=models.CreateAlias(
                    collection_name=collection_name,
                    alias_name=alias_name,
                )
            )
        )
        await self._run(lambda: self._client.update_collection_aliases(operations))

    async def remove_alias(self, alias_name: str) -> None:
        if await self.alias_target(alias_name) is None:
            return
        operation = models.DeleteAliasOperation(
            delete_alias=models.DeleteAlias(alias_name=alias_name)
        )
        await self._run(lambda: self._client.update_collection_aliases([operation]))

    async def list_collections(self) -> set[str]:
        result = await self._run(self._client.get_collections)
        return {item.name for item in result.collections}

    async def delete_collection(self, collection_name: str) -> None:
        await self._run(lambda: self._client.delete_collection(collection_name))

    async def _run(self, operation: Callable[[], Awaitable[T]]) -> T:
        attempts = self._settings.qdrant_max_retries + 1
        for attempt in range(attempts):
            self._raise_if_cancelled()
            try:
                return await operation()
            except UnexpectedResponse as exc:
                retryable = exc.status_code in {429, 502, 503, 504}
                if not retryable or attempt + 1 >= attempts:
                    raise QdrantIndexError(
                        "QDRANT_REQUEST_FAILED",
                        f"Qdrant отклонил запрос ({exc.status_code})",
                        retryable=retryable,
                    ) from exc
            except (ResponseHandlingException, httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt + 1 >= attempts:
                    raise QdrantIndexError(
                        "QDRANT_UNAVAILABLE", "Qdrant недоступен", retryable=True
                    ) from exc
            await self._backoff(attempt)
        raise AssertionError("Недостижимый конец Qdrant retry loop")

    async def _backoff(self, attempt: int) -> None:
        delay = min(5.0, 0.25 * (2**attempt))
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
            raise QdrantIndexError("INDEX_CANCELLED", "Операция с Qdrant отменена")


def _mapping_at(value: Mapping[str, object], *path: str) -> Mapping[str, object]:
    current: object = value
    for part in path:
        if not isinstance(current, Mapping):
            return {}
        current = current.get(part)
    return current if isinstance(current, Mapping) else {}
