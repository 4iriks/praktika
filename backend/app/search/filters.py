from __future__ import annotations

from datetime import datetime
from uuid import UUID

from qdrant_client import models

from app.core.enums import DeduplicationStatus, DocumentStatus, ProcessingStatus


def build_search_filter(
    *,
    tags: list[str],
    date_from: datetime | None,
    date_to: datetime | None,
    min_question_score: int | None,
    accepted_only: bool,
    has_code: bool,
    source_id: UUID | None,
    section_type: str | None,
) -> models.Filter:
    must: list[models.FieldCondition] = [
        models.FieldCondition(
            key="document_status",
            match=models.MatchAny(any=[DocumentStatus.ACTIVE, DocumentStatus.OUTDATED]),
        ),
        models.FieldCondition(
            key="processing_status", match=models.MatchValue(value=ProcessingStatus.CHUNKED)
        ),
        models.FieldCondition(
            key="deduplication_status",
            match=models.MatchValue(value=DeduplicationStatus.UNIQUE),
        ),
    ]
    if tags:
        must.append(models.FieldCondition(key="tags", match=models.MatchAny(any=sorted(set(tags)))))
    if date_from is not None or date_to is not None:
        must.append(
            models.FieldCondition(
                key="published_at", range=models.DatetimeRange(gte=date_from, lte=date_to)
            )
        )
    if min_question_score is not None:
        must.append(
            models.FieldCondition(
                key="question_score", range=models.Range(gte=float(min_question_score))
            )
        )
    if accepted_only:
        must.append(
            models.FieldCondition(key="accepted_answer", match=models.MatchValue(value=True))
        )
    if has_code:
        must.append(models.FieldCondition(key="has_code", match=models.MatchValue(value=True)))
    if source_id is not None:
        must.append(
            models.FieldCondition(key="source_id", match=models.MatchValue(value=str(source_id)))
        )
    if section_type is not None:
        must.append(
            models.FieldCondition(key="section_type", match=models.MatchValue(value=section_type))
        )
    return models.Filter(must=must)
