from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RagEvaluationMetrics:
    source_recall: float
    citation_validity: float
    key_point_coverage: float
    insufficient_context_accuracy: float


def evaluate_rag_records(records: list[dict[str, object]]) -> RagEvaluationMetrics:
    if not records:
        raise ValueError("RAG evaluation требует хотя бы одну запись")
    source_scores: list[float] = []
    citation_scores: list[float] = []
    point_scores: list[float] = []
    insufficient_scores: list[float] = []
    for record in records:
        expected_sources = set(_strings(record.get("expectedSourceIds")))
        returned_sources = set(_strings(record.get("returnedSourceIds")))
        source_scores.append(
            len(expected_sources & returned_sources) / len(expected_sources)
            if expected_sources
            else float(not returned_sources)
        )
        citation_scores.append(float(bool(record.get("citationValidationPassed"))))
        expected_points = [item.casefold() for item in _strings(record.get("requiredPoints"))]
        answer = str(record.get("answer", "")).casefold()
        point_scores.append(
            sum(point in answer for point in expected_points) / len(expected_points)
            if expected_points
            else 1.0
        )
        insufficient_scores.append(
            float(
                bool(record.get("expectedInsufficient")) == bool(record.get("insufficientContext"))
            )
        )
    return RagEvaluationMetrics(
        source_recall=_mean(source_scores),
        citation_validity=_mean(citation_scores),
        key_point_coverage=_mean(point_scores),
        insufficient_context_accuracy=_mean(insufficient_scores),
    )


def stable_rag_dataset_hash(records: list[dict[str, object]]) -> str:
    encoded = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]
