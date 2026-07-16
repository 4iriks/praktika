from __future__ import annotations

from uuid import uuid4

import pytest

from app.core.config import Settings
from app.integrations.qdrant import (
    IndexPoint,
    QdrantIndexClient,
    index_schema_from_settings,
    sparse_provider_from_settings,
)

pytestmark = pytest.mark.qdrant


async def test_real_qdrant_dense_sparse_schema_payload_indexes_and_alias() -> None:
    settings = Settings(
        APP_ENV="test",
        QDRANT_URL="http://127.0.0.1:6333",
        QDRANT_MAX_RETRIES=0,
        EMBEDDING_DIMENSIONS=8,
    )
    client = QdrantIndexClient(settings)
    collection = f"pyanswer_test_{uuid4().hex}"
    alias = f"pyanswer_test_alias_{uuid4().hex}"
    try:
        health = await client.health()
        assert health.online and health.version == "1.18.2"
        schema = index_schema_from_settings(settings)
        await client.create_collection(collection, schema)
        await client.validate_collection(collection, schema)
        sparse = sparse_provider_from_settings(settings).embed_documents(["Python asyncio gather"])[
            0
        ]
        point = IndexPoint(
            point_id=uuid4(),
            dense=tuple([0.125] * 8),
            sparse=sparse,
            payload={
                "document_id": str(uuid4()),
                "source_id": str(uuid4()),
                "tags": ["python"],
                "published_at": "2026-07-16T00:00:00Z",
                "question_score": 1,
                "accepted_answer": True,
                "has_code": True,
                "section_type": "QUESTION",
                "document_status": "ACTIVE",
                "processing_status": "CHUNKED",
                "deduplication_status": "UNIQUE",
                "document_version": 1,
            },
        )
        await client.upsert(collection, [point])
        assert await client.count(collection) == 1
        assert await client.sample_dense_query(collection, point.dense) == 1
        await client.switch_alias(alias, collection)
        assert await client.alias_target(alias) == collection
        await client.remove_alias(alias)
        assert await client.alias_target(alias) is None
    finally:
        if collection in await client.list_collections():
            await client.delete_collection(collection)
        await client.close()
