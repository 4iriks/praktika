from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetrievalMetrics:
    recall_at_5: float
    recall_at_10: float
    mrr_at_10: float
    ndcg_at_10: float
    hit_rate_at_5: float


def evaluate_rankings(rankings: list[list[str]], relevant: list[set[str]]) -> RetrievalMetrics:
    if not rankings or len(rankings) != len(relevant):
        raise ValueError("Rankings и relevance labels должны иметь одинаковую ненулевую длину")
    return RetrievalMetrics(
        recall_at_5=_mean(
            [_recall(row[:5], expected) for row, expected in zip(rankings, relevant, strict=True)]
        ),
        recall_at_10=_mean(
            [_recall(row[:10], expected) for row, expected in zip(rankings, relevant, strict=True)]
        ),
        mrr_at_10=_mean(
            [
                _reciprocal_rank(row[:10], expected)
                for row, expected in zip(rankings, relevant, strict=True)
            ]
        ),
        ndcg_at_10=_mean(
            [_ndcg(row[:10], expected) for row, expected in zip(rankings, relevant, strict=True)]
        ),
        hit_rate_at_5=_mean(
            [
                float(bool(set(row[:5]) & expected))
                for row, expected in zip(rankings, relevant, strict=True)
            ]
        ),
    )


def stable_dataset_hash(records: list[dict[str, object]]) -> str:
    encoded = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def percentile(values: list[float], percentile_value: float) -> float:
    if not values or not 0 <= percentile_value <= 1:
        raise ValueError("Некорректные данные percentile")
    ordered = sorted(values)
    index = max(0, math.ceil(percentile_value * len(ordered)) - 1)
    return ordered[index]


def _recall(ranking: list[str], relevant: set[str]) -> float:
    return len(set(ranking) & relevant) / len(relevant) if relevant else 0


def _reciprocal_rank(ranking: list[str], relevant: set[str]) -> float:
    for rank, item in enumerate(ranking, start=1):
        if item in relevant:
            return 1 / rank
    return 0


def _ndcg(ranking: list[str], relevant: set[str]) -> float:
    dcg = sum(
        1 / math.log2(rank + 1) for rank, item in enumerate(ranking, start=1) if item in relevant
    )
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(len(relevant), 10) + 1))
    return dcg / ideal if ideal else 0


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)
