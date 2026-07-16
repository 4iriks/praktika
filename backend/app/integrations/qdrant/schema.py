from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from uuid import UUID, uuid5

from qdrant_client import models

from app.core.config import Settings
from app.core.enums import DeduplicationStatus, DocumentStatus, ProcessingStatus
from app.db.models.content import Document, DocumentChunk
from app.integrations.qdrant.sparse import SparseRepresentation

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"
POINT_NAMESPACE = UUID("f4bd773f-05dd-5cb6-aeb0-b26d5176330d")


@dataclass(frozen=True, slots=True)
class IndexSchema:
    schema_version: str
    chunk_schema_version: str
    payload_schema_version: str
    dense_provider: str
    dense_model: str
    dense_dimensions: int
    document_preprocessing_version: str
    query_instruction_hash: str
    sparse_provider: str
    sparse_model: str
    hnsw_m: int
    hnsw_ef_construct: int
    quantization: str | None = None

    @property
    def hash(self) -> str:
        encoded = json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class IndexPoint:
    point_id: UUID
    dense: tuple[float, ...]
    sparse: SparseRepresentation
    payload: dict[str, object]

    def to_qdrant(self) -> models.PointStruct:
        return models.PointStruct(
            id=self.point_id,
            vector={
                DENSE_VECTOR_NAME: list(self.dense),
                SPARSE_VECTOR_NAME: self.sparse,
            },
            payload=self.payload,
        )


def index_schema_from_settings(settings: Settings) -> IndexSchema:
    instruction_hash = hashlib.sha256(settings.embedding_query_instruction.encode()).hexdigest()
    return IndexSchema(
        schema_version=settings.index_schema_version,
        chunk_schema_version=settings.index_chunk_schema_version,
        payload_schema_version=settings.index_payload_schema_version,
        dense_provider=settings.embedding_provider,
        dense_model=settings.embedding_model,
        dense_dimensions=settings.embedding_dimensions,
        document_preprocessing_version="contextual_text:v1",
        query_instruction_hash=instruction_hash,
        sparse_provider=settings.sparse_provider,
        sparse_model=settings.sparse_model,
        hnsw_m=settings.index_hnsw_m,
        hnsw_ef_construct=settings.index_hnsw_ef_construct,
    )


def stable_point_id(
    chunk_id: UUID,
    document_version: int,
    chunk_content_hash: str,
    index_schema_version: str,
) -> UUID:
    identity = f"{chunk_id}:{document_version}:{chunk_content_hash}:{index_schema_version}"
    return uuid5(POINT_NAMESPACE, identity)


def document_is_eligible(document: Document, *, allow_possible_duplicates: bool = False) -> bool:
    allowed_dedup = {DeduplicationStatus.UNIQUE}
    if allow_possible_duplicates:
        allowed_dedup.add(DeduplicationStatus.POSSIBLE_DUPLICATE)
    return (
        document.processing_status == ProcessingStatus.CHUNKED
        and document.status in {DocumentStatus.ACTIVE, DocumentStatus.OUTDATED}
        and document.deduplication_status in allowed_dedup
        and not document.processing_error
    )


def chunk_is_eligible(
    document: Document,
    chunk: DocumentChunk,
    *,
    allow_possible_duplicates: bool = False,
) -> bool:
    return (
        document_is_eligible(document, allow_possible_duplicates=allow_possible_duplicates)
        and chunk.document_version == document.version
        and bool(chunk.text.strip())
        and bool(chunk.contextual_text.strip())
    )


def build_index_payload(
    document: Document,
    chunk: DocumentChunk,
    *,
    tags: list[str],
    indexed_at: datetime,
    index_schema_version: str,
) -> dict[str, object]:
    source = document.source
    payload: dict[str, object] = {
        "chunk_id": str(chunk.id),
        "document_id": str(document.id),
        "document_version": document.version,
        "chunk_ordinal": chunk.ordinal,
        "chunk_content_hash": chunk.content_hash,
        "document_content_hash": document.content_hash,
        "source_id": str(document.source_id),
        "source_type": source.type,
        "source_url": document.source_url,
        "title": document.normalized_title,
        "tags": sorted(set(tags)),
        "published_at": document.published_at.isoformat(),
        "question_score": document.score,
        "answers_count": document.answers_count,
        "accepted_answer": document.accepted_answer_external_id is not None,
        "has_code": chunk.has_code or document.has_code,
        "section_type": chunk.section_type,
        "language": chunk.language or "",
        "document_status": document.status,
        "processing_status": document.processing_status,
        "deduplication_status": document.deduplication_status,
        "indexed_at": indexed_at.isoformat(),
        "index_schema_version": index_schema_version,
        "text_preview": chunk.text[:280],
    }
    return payload
