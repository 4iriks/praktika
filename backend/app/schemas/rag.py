from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.core.enums import ConfidenceLabel, SearchMode
from app.schemas.base import ApiModel
from app.schemas.content import TagOut


class RagFilters(ApiModel):
    tags: list[str] = Field(default_factory=list, max_length=20)
    min_score: int = 0
    accepted_only: bool = False
    has_code_only: bool = False
    sort: Literal["relevance", "date", "score"] = "relevance"

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        return sorted({item.strip().casefold() for item in value if item.strip()})


class AskRequest(ApiModel):
    question: str = Field(min_length=1, max_length=10000)
    mode: SearchMode = SearchMode.HYBRID
    max_sources: int | None = Field(default=None, ge=1, le=20)
    document_id: UUID | None = None
    filters: RagFilters = Field(default_factory=RagFilters)
    page_size: int | None = Field(default=None, ge=1, le=100)
    stream: bool = False
    client_request_id: str | None = Field(default=None, min_length=8, max_length=80)


class RagSourceOut(ApiModel):
    citation_index: int
    chunk_id: UUID
    document_id: UUID
    title: str
    snippet: str
    source_url: str
    tags: list[TagOut]
    section_type: str
    score: float
    bm25_score: float | None = None
    vector_score: float | None = None
    fusion_score: float
    reranker_score: float | None = None
    saved: bool


class AskResponseOut(ApiModel):
    response_id: UUID
    answer: str
    sources: list[RagSourceOut]
    model: str
    model_version: str | None = None
    took_ms: int
    search_took_ms: int
    reranker_took_ms: int
    generation_took_ms: int
    confidence: float
    confidence_label: ConfidenceLabel
    confidence_formula_version: str
    insufficient_context: bool
    citation_validation_passed: bool
    index_version: str
    prompt_version: str


class RagDiagnosticsOut(ApiModel):
    provider: str
    model: str
    model_installed: bool
    model_loaded: bool
    online: bool
    context_tokens: int
    queue_active: int
    queue_waiting: int
    queue_limit: int
    prompt_version: str
    active_index: str | None
    recent_failures: int
    insufficient_context_rate: float
    citation_validation_rate: float
    average_generation_ms: int
    checked_at: datetime
