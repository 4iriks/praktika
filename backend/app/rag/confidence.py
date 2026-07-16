from __future__ import annotations

from dataclasses import dataclass

from app.core.enums import ConfidenceLabel
from app.rag.context import ContextSource


@dataclass(frozen=True, slots=True)
class ConfidenceResult:
    value: float
    label: ConfidenceLabel
    formula_version: str = "retrieval-v1"


def calculate_confidence(
    sources: tuple[ContextSource, ...], cited_indexes: tuple[int, ...], *, insufficient: bool
) -> ConfidenceResult:
    if insufficient or not sources:
        return ConfidenceResult(0.1, ConfidenceLabel.LOW)
    scores = [
        source.reranker_score if source.reranker_score is not None else source.final_score
        for source in sources
    ]
    top = max(scores, default=0)
    mean = sum(scores) / len(scores)
    source_factor = min(1.0, len(sources) / 3)
    citation_factor = min(1.0, len(set(cited_indexes)) / len(sources))
    value = max(
        0.0, min(1.0, 0.45 * top + 0.25 * mean + 0.15 * source_factor + 0.15 * citation_factor)
    )
    label = (
        ConfidenceLabel.HIGH
        if value >= 0.72
        else ConfidenceLabel.MEDIUM
        if value >= 0.4
        else ConfidenceLabel.LOW
    )
    return ConfidenceResult(round(value, 3), label)
