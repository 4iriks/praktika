"""Deterministic retrieval primitives used by the HTTP search service."""

from app.search.fusion import RankedCandidate, RetrievedCandidate, weighted_rrf
from app.search.query import normalize_query

__all__ = ["RankedCandidate", "RetrievedCandidate", "normalize_query", "weighted_rrf"]
