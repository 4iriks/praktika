from __future__ import annotations

from datetime import datetime

from app.core.enums import SearchMode
from app.schemas.base import ApiModel, Pagination
from app.schemas.content import TagOut


class MatchedChunkOut(ApiModel):
    chunk_id: str
    section_type: str
    snippet: str
    bm25_score: float | None
    vector_score: float | None
    fusion_score: float
    reranker_score: float | None


class SearchResultOut(ApiModel):
    document_id: str
    chunk_id: str
    title: str
    snippet: str
    matched_text: str
    section_type: str
    tags: list[TagOut]
    source_url: str
    published_at: datetime
    question_score: int
    answers_count: int
    accepted_answer: bool
    has_code: bool
    saved: bool
    bm25_score: float | None
    bm25_rank: int | None
    vector_score: float | None
    vector_rank: int | None
    fusion_score: float
    reranker_score: float | None
    final_score: float
    rank: int
    matched_chunks: list[MatchedChunkOut]
    index_version: str
    document_version: int


class SearchTimingsOut(ApiModel):
    total_ms: int
    embedding_ms: int
    bm25_ms: int
    vector_ms: int
    fusion_ms: int
    reranker_ms: int
    postgres_hydration_ms: int


class SearchMetricsOut(ApiModel):
    took_ms: int
    candidates: int
    reranked: int
    query_tokens: int
    candidate_count: int
    returned_documents: int
    has_more_within_candidate_window: bool
    total_is_exact: bool = False
    reranker_applied: bool
    stale_discarded: int
    index_version: str
    mode: SearchMode
    timings: SearchTimingsOut


class SearchResponseOut(ApiModel):
    results: list[SearchResultOut]
    pagination: Pagination
    metrics: SearchMetricsOut
