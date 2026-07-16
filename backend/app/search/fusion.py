from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RetrievedCandidate:
    point_id: UUID
    score: float
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    point_id: UUID
    payload: dict[str, object]
    bm25_score: float | None
    bm25_rank: int | None
    vector_score: float | None
    vector_rank: int | None
    fusion_score: float


@dataclass(slots=True)
class _Accumulator:
    payload: dict[str, object]
    fusion: float = 0
    bm25_score: float | None = None
    bm25_rank: int | None = None
    vector_score: float | None = None
    vector_rank: int | None = None


def weighted_rrf(
    bm25: list[RetrievedCandidate],
    vector: list[RetrievedCandidate],
    *,
    k: int,
    bm25_weight: float,
    vector_weight: float,
    limit: int,
) -> list[RankedCandidate]:
    if k < 1 or limit < 1 or bm25_weight <= 0 or vector_weight <= 0:
        raise ValueError("Некорректная конфигурация weighted RRF")
    rows: dict[UUID, _Accumulator] = {}
    for rank, candidate in enumerate(bm25, start=1):
        row = rows.setdefault(candidate.point_id, _Accumulator(payload=candidate.payload))
        row.bm25_score = candidate.score
        row.bm25_rank = rank
        row.fusion += bm25_weight / (k + rank)
    for rank, candidate in enumerate(vector, start=1):
        row = rows.setdefault(candidate.point_id, _Accumulator(payload=candidate.payload))
        row.vector_score = candidate.score
        row.vector_rank = rank
        row.fusion += vector_weight / (k + rank)
    ranked = [
        RankedCandidate(
            point_id=point_id,
            payload=row.payload,
            bm25_score=row.bm25_score,
            bm25_rank=row.bm25_rank,
            vector_score=row.vector_score,
            vector_rank=row.vector_rank,
            fusion_score=row.fusion,
        )
        for point_id, row in rows.items()
    ]
    ranked.sort(
        key=lambda item: (
            -item.fusion_score,
            min(item.bm25_rank or 10**9, item.vector_rank or 10**9),
            str(item.point_id),
        )
    )
    return ranked[:limit]
