from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator

from app.core.enums import FeedbackValue, IndexStatus, SearchMode, SearchView
from app.schemas.base import ApiModel, Pagination


class TagOut(ApiModel):
    name: str
    slug: str


class ScoreBreakdownOut(ApiModel):
    bm25_score: float = 0
    vector_score: float = 0
    reranker_score: float = 0
    final_score: float = 0


class QuestionOut(ApiModel):
    body: str
    code_blocks: list[str]


class AnswerOut(ApiModel):
    id: str
    author: str
    body: str
    code_blocks: list[str]
    score: int
    accepted: bool
    created_at: datetime


class DocumentOut(ApiModel):
    id: str
    title: str
    source_url: str
    published_at: datetime
    author: str
    views: int
    score: int
    tags: list[TagOut]
    question: QuestionOut
    answers: list[AnswerOut]
    chunk_count: int
    indexed_at: datetime
    bm25_status: IndexStatus
    vector_status: IndexStatus
    content_hash: str
    saved: bool
    scores: ScoreBreakdownOut


class SearchHistoryOut(ApiModel):
    id: UUID
    user_id: UUID
    query: str
    view: SearchView
    mode: SearchMode
    filters: dict[str, object]
    sort: str
    page_size: int
    result_count: int
    took_ms: int
    created_at: datetime
    answer_preview: str | None = None
    insufficient_context: bool | None = None


class HistoryResponse(ApiModel):
    items: list[SearchHistoryOut]
    pagination: Pagination


class SavedDocumentOut(ApiModel):
    document_id: str
    title: str
    snippet: str
    tags: list[TagOut]
    source_url: str
    published_at: datetime
    question_score: int
    answers_count: int
    accepted_answer: bool
    has_code: bool
    saved: bool = True
    bm25_score: float = 0
    vector_score: float = 0
    reranker_score: float = 0
    final_score: float = 0
    saved_at: datetime


class SavedDocumentsResponse(ApiModel):
    items: list[SavedDocumentOut]
    available_tags: list[TagOut]
    pagination: Pagination


class FeedbackRequest(ApiModel):
    response_id: str = Field(min_length=1, max_length=120)
    value: FeedbackValue
    reason: str | None = Field(default=None, max_length=40)
    question: str = Field(min_length=1, max_length=1000)
    comment: str | None = Field(default=None, max_length=1000)

    @field_validator("comment", "reason")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        stripped = value.strip() if value is not None else None
        return stripped or None

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str | None) -> str | None:
        valid = {"irrelevant_sources", "factual_error", "incomplete", "unclear", "other"}
        if value is not None and value not in valid:
            raise ValueError("Неизвестная причина оценки")
        return value


class FeedbackOut(ApiModel):
    id: UUID
    user_id: UUID
    response_id: str
    value: FeedbackValue
    reason: str | None = None
    question: str
    comment: str | None = None
    created_at: datetime
    updated_at: datetime


class PublicServiceStatusOut(ApiModel):
    name: str
    state: str
    latency_ms: int | None = None


class PublicSystemStatusOut(ApiModel):
    services: list[PublicServiceStatusOut]
    model: str
    model_context: int
    indexed_documents: int
    indexed_chunks: int
    updated_at: datetime


class PublicAccessPolicyOut(ApiModel):
    allow_guest_search: bool
    allow_guest_rag: bool
    rag_sources_limit: int
