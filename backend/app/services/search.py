from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.errors import ApiException
from app.core.config import Settings
from app.core.enums import (
    DeduplicationStatus,
    DocumentStatus,
    ProcessingStatus,
    SearchIndexVersionStatus,
    SearchMode,
    SearchView,
)
from app.core.rate_limit import InMemoryRateLimiter
from app.db.models.content import Document, DocumentChunk, DocumentTag
from app.db.models.identity import SavedDocument, SearchHistory, User
from app.db.models.operations import SearchIndexVersion, SearchRun
from app.integrations.embeddings import EmbeddingProvider, EmbeddingProviderError
from app.integrations.embeddings.ollama import OllamaEmbeddingProvider
from app.integrations.qdrant import QdrantIndexClient, QdrantIndexError
from app.integrations.qdrant.sparse import SparseEmbeddingProvider, sparse_provider_from_settings
from app.integrations.reranker import RerankerClient, RerankerError
from app.schemas.base import pagination
from app.schemas.content import TagOut
from app.schemas.search import (
    MatchedChunkOut,
    SearchMetricsOut,
    SearchResponseOut,
    SearchResultOut,
    SearchTimingsOut,
)
from app.search.filters import build_search_filter
from app.search.fusion import RankedCandidate, RetrievedCandidate, weighted_rrf
from app.search.query import QueryValidationError, normalize_query
from app.services.content import selected_tags
from app.services.system import get_settings_record


@dataclass(frozen=True, slots=True)
class SearchFilters:
    tags: list[str]
    date_from: datetime | None
    date_to: datetime | None
    min_question_score: int | None
    accepted_only: bool
    has_code: bool
    source_id: UUID | None
    section_type: str | None
    sort: str

    def json(self) -> dict[str, object]:
        return {
            "tags": self.tags,
            "dateFrom": self.date_from.isoformat() if self.date_from else None,
            "dateTo": self.date_to.isoformat() if self.date_to else None,
            "minQuestionScore": self.min_question_score,
            "acceptedOnly": self.accepted_only,
            "hasCode": self.has_code,
            "sourceId": str(self.source_id) if self.source_id else None,
            "sectionType": self.section_type,
            "sort": self.sort,
        }


@dataclass(slots=True)
class HydratedCandidate:
    ranked: RankedCandidate
    chunk: DocumentChunk
    document: Document
    reranker_score: float | None = None
    final_score: float = 0


class QueryEmbeddingCache:
    def __init__(self, capacity: int, ttl_seconds: int) -> None:
        self._capacity = capacity
        self._ttl = ttl_seconds
        self._values: OrderedDict[str, tuple[float, tuple[float, ...]]] = OrderedDict()

    def get(self, key: str, *, now: float | None = None) -> tuple[float, ...] | None:
        current = time.monotonic() if now is None else now
        item = self._values.get(key)
        if item is None:
            return None
        expires_at, value = item
        if expires_at <= current:
            del self._values[key]
            return None
        self._values.move_to_end(key)
        return value

    def put(self, key: str, value: tuple[float, ...], *, now: float | None = None) -> None:
        if self._capacity == 0:
            return
        current = time.monotonic() if now is None else now
        self._values[key] = (current + self._ttl, value)
        self._values.move_to_end(key)
        while len(self._values) > self._capacity:
            self._values.popitem(last=False)

    @property
    def size(self) -> int:
        return len(self._values)


_embedding_cache: QueryEmbeddingCache | None = None
_embedding_cache_config: tuple[int, int] | None = None
_rate_limiters: dict[tuple[int, int, bool], InMemoryRateLimiter] = {}


async def search_documents(
    db: AsyncSession,
    *,
    config: Settings,
    user: User | None,
    request_id: str,
    client_key: str,
    query: str,
    view: str,
    mode: SearchMode,
    page: int,
    page_size: int,
    apply_reranker: bool = True,
    filters: SearchFilters,
    embeddings: EmbeddingProvider | None = None,
    sparse: SparseEmbeddingProvider | None = None,
    qdrant: QdrantIndexClient | None = None,
    reranker: RerankerClient | None = None,
) -> SearchResponseOut:
    started = time.perf_counter()
    if view != SearchView.DOCUMENTS:
        raise ApiException(422, "VALIDATION_ERROR", "Для /search поддерживается view=documents")
    if page * page_size > config.search_max_candidates:
        raise ApiException(
            422,
            "VALIDATION_ERROR",
            "Глубина пагинации превышает окно поисковых кандидатов",
        )
    try:
        normalized = normalize_query(
            query,
            max_characters=config.search_query_max_chars,
            max_tokens=config.search_query_max_tokens,
        )
    except QueryValidationError as exc:
        raise ApiException(422, "VALIDATION_ERROR", exc.safe_message) from exc
    _check_rate_limit(config, user, client_key)
    system = await get_settings_record(db)
    if user is None and not system.allow_guest_search:
        raise ApiException(401, "UNAUTHORIZED", "Для поиска требуется авторизация")
    active = await db.scalar(
        select(SearchIndexVersion).where(
            SearchIndexVersion.status == SearchIndexVersionStatus.ACTIVE
        )
    )
    if active is None:
        raise ApiException(503, "SERVICE_UNAVAILABLE", "Активный поисковый индекс отсутствует")
    candidate_cap = min(system.search_candidates_limit, config.search_max_candidates)
    await db.commit()  # No PostgreSQL transaction remains open during local inference/Qdrant I/O.

    own_embeddings = embeddings is None
    own_qdrant = qdrant is None
    own_reranker = reranker is None
    embeddings = embeddings or OllamaEmbeddingProvider(config)
    sparse = sparse or sparse_provider_from_settings(config)
    qdrant = qdrant or QdrantIndexClient(config)
    reranker = reranker or RerankerClient(config)
    embedding_ms = bm25_ms = vector_ms = fusion_ms = reranker_ms = hydration_ms = 0
    query_filter = build_search_filter(
        tags=filters.tags,
        date_from=filters.date_from,
        date_to=filters.date_to,
        min_question_score=filters.min_question_score,
        accepted_only=filters.accepted_only,
        has_code=filters.has_code,
        source_id=filters.source_id,
        section_type=filters.section_type,
    )
    bm25: list[RetrievedCandidate] = []
    vector: list[RetrievedCandidate] = []
    try:
        if mode in {SearchMode.BM25, SearchMode.HYBRID}:
            mark = time.perf_counter()
            sparse_query = sparse.embed_documents([normalized])[0]
            bm25 = await qdrant.query_sparse(
                active.alias_name,
                sparse_query,
                query_filter=query_filter,
                limit=min(config.search_bm25_candidates, candidate_cap),
            )
            bm25_ms = _milliseconds(mark)
        if mode in {SearchMode.VECTOR, SearchMode.HYBRID}:
            mark = time.perf_counter()
            dense = await _query_embedding(config, embeddings, normalized)
            embedding_ms = _milliseconds(mark)
            mark = time.perf_counter()
            vector = await qdrant.query_dense(
                active.alias_name,
                dense,
                query_filter=query_filter,
                limit=min(config.search_vector_candidates, candidate_cap),
            )
            vector_ms = _milliseconds(mark)
        mark = time.perf_counter()
        ranked = weighted_rrf(
            bm25,
            vector,
            k=config.search_rrf_k,
            bm25_weight=config.search_bm25_weight,
            vector_weight=config.search_vector_weight,
            limit=min(config.search_hybrid_candidates, candidate_cap),
        )
        fusion_ms = _milliseconds(mark)
    except EmbeddingProviderError as exc:
        raise ApiException(503, "SERVICE_UNAVAILABLE", exc.safe_message) from exc
    except QdrantIndexError as exc:
        raise ApiException(503, "SERVICE_UNAVAILABLE", exc.safe_message) from exc
    finally:
        if own_embeddings:
            await embeddings.close()
        if own_qdrant:
            await qdrant.close()

    mark = time.perf_counter()
    hydrated, stale_discarded = await _hydrate(db, ranked, filters)
    hydration_ms = _milliseconds(mark)
    reranker_applied = False
    try:
        top = hydrated[: min(system.reranker_limit, config.reranker_top_n)]
        if top and apply_reranker:
            mark = time.perf_counter()
            result = await reranker.rerank(normalized, [item.chunk.text for item in top])
            reranker_ms = _milliseconds(mark)
            for item, score in zip(top, result.scores, strict=True):
                item.reranker_score = score
            reranker_applied = True
    except RerankerError as exc:
        if config.reranker_required:
            raise ApiException(503, "SERVICE_UNAVAILABLE", exc.safe_message) from exc
    finally:
        if own_reranker:
            await reranker.close()
    _assign_final_scores(hydrated, reranker_applied, config.reranker_fusion_blend)
    if reranker_applied:
        hydrated.sort(key=lambda item: (-item.final_score, str(item.ranked.point_id)))
    grouped = _group_candidates(hydrated, config.search_max_chunks_per_document)
    if filters.sort == "date":
        grouped.sort(
            key=lambda group: (
                -group[0].document.published_at.timestamp(),
                str(group[0].document.id),
            )
        )
    elif filters.sort == "score":
        grouped.sort(key=lambda group: (-group[0].document.score, str(group[0].document.id)))
    total = len(grouped)
    offset = (page - 1) * page_size
    page_groups = grouped[offset : offset + page_size]
    saved_ids = await _saved_document_ids(db, user, [group[0].document.id for group in page_groups])
    results = _results(
        page_groups,
        saved_ids=saved_ids,
        normalized_query=normalized,
        max_snippet=config.search_snippet_characters,
        index_version=active.schema_hash,
        offset=offset,
    )
    total_ms = _milliseconds(started)
    request_id = request_id[:80]
    timings = SearchTimingsOut(
        total_ms=total_ms,
        embedding_ms=embedding_ms,
        bm25_ms=bm25_ms,
        vector_ms=vector_ms,
        fusion_ms=fusion_ms,
        reranker_ms=reranker_ms,
        postgres_hydration_ms=hydration_ms,
    )
    await _persist_search(
        db,
        request_id=request_id,
        user=user,
        query=normalized,
        mode=mode,
        filters=filters,
        page_size=page_size,
        candidate_count=len(ranked),
        result_count=len(results),
        reranker_applied=reranker_applied,
        index_version=active,
        timings=timings,
    )
    return SearchResponseOut(
        results=results,
        pagination=pagination(page, page_size, total),
        metrics=SearchMetricsOut(
            took_ms=total_ms,
            candidates=len(ranked),
            reranked=min(len(hydrated), config.reranker_top_n) if reranker_applied else 0,
            query_tokens=max(1, (len(normalized) + 3) // 4),
            candidate_count=len(ranked),
            returned_documents=len(results),
            has_more_within_candidate_window=offset + len(results) < total,
            reranker_applied=reranker_applied,
            stale_discarded=stale_discarded,
            index_version=active.schema_hash,
            mode=mode,
            timings=timings,
        ),
    )


async def _query_embedding(
    config: Settings, provider: EmbeddingProvider, query: str
) -> tuple[float, ...]:
    global _embedding_cache, _embedding_cache_config
    cache_config = (config.search_embedding_cache_size, config.search_embedding_cache_ttl_seconds)
    if _embedding_cache is None or _embedding_cache_config != cache_config:
        _embedding_cache = QueryEmbeddingCache(*cache_config)
        _embedding_cache_config = cache_config
    key_material = (
        f"{query}\0{provider.model_name}\0{provider.dimensions}\0{provider.configuration_hash}"
    )
    key = hashlib.sha256(key_material.encode()).hexdigest()
    cached = _embedding_cache.get(key)
    if cached is not None:
        return cached
    batch = await provider.embed_query(query)
    vector = batch.vectors[0]
    _embedding_cache.put(key, vector)
    return vector


def _check_rate_limit(config: Settings, user: User | None, client_key: str) -> None:
    authenticated = user is not None
    limit = (
        config.search_authenticated_rate_limit_requests
        if authenticated
        else config.search_guest_rate_limit_requests
    )
    key = (limit, config.search_rate_limit_window_seconds, authenticated)
    limiter = _rate_limiters.setdefault(
        key,
        InMemoryRateLimiter(limit=limit, window_seconds=config.search_rate_limit_window_seconds),
    )
    limiter.check(("user:" + str(user.id)) if user else ("guest:" + client_key))


async def _hydrate(
    db: AsyncSession, ranked: list[RankedCandidate], filters: SearchFilters
) -> tuple[list[HydratedCandidate], int]:
    chunk_ids: list[UUID] = []
    for item in ranked:
        raw = item.payload.get("chunk_id")
        try:
            chunk_ids.append(UUID(str(raw)))
        except (ValueError, TypeError, AttributeError):
            continue
    chunks = (
        await db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.id.in_(chunk_ids))
            .options(
                selectinload(DocumentChunk.document).selectinload(Document.source),
                selectinload(DocumentChunk.document)
                .selectinload(Document.tag_links)
                .selectinload(DocumentTag.tag),
            )
        )
    ).all()
    by_id = {item.id: item for item in chunks}
    hydrated: list[HydratedCandidate] = []
    for item in ranked:
        raw = item.payload.get("chunk_id")
        try:
            chunk = by_id.get(UUID(str(raw)))
        except (ValueError, TypeError, AttributeError):
            chunk = None
        if chunk is None or not _db_visible(chunk, filters):
            continue
        hydrated.append(HydratedCandidate(item, chunk, chunk.document))
    return hydrated, len(ranked) - len(hydrated)


def _db_visible(chunk: DocumentChunk, filters: SearchFilters) -> bool:
    document = chunk.document
    tags = {tag.normalized_name for tag in selected_tags(document)}
    return (
        document.status in {DocumentStatus.ACTIVE, DocumentStatus.OUTDATED}
        and document.processing_status == ProcessingStatus.CHUNKED
        and document.deduplication_status == DeduplicationStatus.UNIQUE
        and not document.processing_error
        and chunk.document_version == document.version
        and (not filters.tags or bool(tags.intersection(filters.tags)))
        and (filters.date_from is None or document.published_at >= filters.date_from)
        and (filters.date_to is None or document.published_at <= filters.date_to)
        and (filters.min_question_score is None or document.score >= filters.min_question_score)
        and (not filters.accepted_only or document.accepted_answer_external_id is not None)
        and (not filters.has_code or chunk.has_code or document.has_code)
        and (filters.source_id is None or document.source_id == filters.source_id)
        and (filters.section_type is None or chunk.section_type == filters.section_type)
    )


def _assign_final_scores(
    candidates: list[HydratedCandidate], reranker_applied: bool, blend: float
) -> None:
    max_fusion = max((item.ranked.fusion_score for item in candidates), default=1.0)
    for item in candidates:
        normalized_fusion = item.ranked.fusion_score / max_fusion if max_fusion else 0
        if reranker_applied and item.reranker_score is not None:
            item.final_score = item.reranker_score * (1 - blend) + normalized_fusion * blend
        else:
            item.final_score = normalized_fusion


def _group_candidates(
    candidates: list[HydratedCandidate], max_chunks: int
) -> list[list[HydratedCandidate]]:
    groups: OrderedDict[UUID, list[HydratedCandidate]] = OrderedDict()
    for candidate in candidates:
        group = groups.setdefault(candidate.document.id, [])
        if len(group) < max_chunks:
            group.append(candidate)
    return list(groups.values())


async def _saved_document_ids(
    db: AsyncSession, user: User | None, document_ids: list[UUID]
) -> set[UUID]:
    if user is None or not document_ids:
        return set()
    return set(
        await db.scalars(
            select(SavedDocument.document_id).where(
                SavedDocument.user_id == user.id,
                SavedDocument.document_id.in_(document_ids),
            )
        )
    )


def _results(
    groups: list[list[HydratedCandidate]],
    *,
    saved_ids: set[UUID],
    normalized_query: str,
    max_snippet: int,
    index_version: str,
    offset: int,
) -> list[SearchResultOut]:
    output: list[SearchResultOut] = []
    for position, group in enumerate(groups, start=offset + 1):
        best = group[0]
        document = best.document
        chunk = best.chunk
        snippet = _snippet(chunk.text, normalized_query, max_snippet)
        output.append(
            SearchResultOut(
                document_id=str(document.id),
                chunk_id=str(chunk.id),
                title=document.normalized_title,
                snippet=snippet,
                matched_text=snippet,
                section_type=chunk.section_type,
                tags=[
                    TagOut(name=tag.display_name, slug=tag.normalized_name)
                    for tag in selected_tags(document)
                ],
                source_url=document.source_url,
                published_at=document.published_at,
                question_score=document.score,
                answers_count=document.answers_count,
                accepted_answer=document.accepted_answer_external_id is not None,
                has_code=document.has_code or chunk.has_code,
                saved=document.id in saved_ids,
                bm25_score=best.ranked.bm25_score,
                bm25_rank=best.ranked.bm25_rank,
                vector_score=best.ranked.vector_score,
                vector_rank=best.ranked.vector_rank,
                fusion_score=best.ranked.fusion_score,
                reranker_score=best.reranker_score,
                final_score=best.final_score,
                rank=position,
                matched_chunks=[
                    MatchedChunkOut(
                        chunk_id=str(item.chunk.id),
                        section_type=item.chunk.section_type,
                        snippet=_snippet(item.chunk.text, normalized_query, max_snippet),
                        bm25_score=item.ranked.bm25_score,
                        vector_score=item.ranked.vector_score,
                        fusion_score=item.ranked.fusion_score,
                        reranker_score=item.reranker_score,
                    )
                    for item in group
                ],
                index_version=index_version,
                document_version=document.version,
            )
        )
    return output


def _snippet(text: str, query: str, max_characters: int) -> str:
    cleaned = text.strip()
    if len(cleaned) <= max_characters:
        return cleaned
    lowered = cleaned.casefold()
    terms = [term.casefold() for term in query.split() if len(term) > 1]
    positions = [lowered.find(term) for term in terms]
    found = [position for position in positions if position >= 0]
    center = min(found) if found else 0
    start = max(0, center - max_characters // 3)
    end = min(len(cleaned), start + max_characters)
    prefix = "…" if start else ""
    suffix = "…" if end < len(cleaned) else ""
    return prefix + cleaned[start:end].strip() + suffix


async def _persist_search(
    db: AsyncSession,
    *,
    request_id: str,
    user: User | None,
    query: str,
    mode: SearchMode,
    filters: SearchFilters,
    page_size: int,
    candidate_count: int,
    result_count: int,
    reranker_applied: bool,
    index_version: SearchIndexVersion,
    timings: SearchTimingsOut,
) -> None:
    values = {
        "request_id": request_id,
        "user_id": user.id if user else None,
        "query": query,
        "query_hash": hashlib.sha256(query.encode()).hexdigest(),
        "mode": mode,
        "filters": filters.json(),
        "requested_limit": page_size,
        "candidate_count": candidate_count,
        "result_count": result_count,
        "reranker_applied": reranker_applied,
        "index_version_id": index_version.id,
        "total_ms": timings.total_ms,
        "embedding_ms": timings.embedding_ms,
        "bm25_ms": timings.bm25_ms,
        "vector_ms": timings.vector_ms,
        "fusion_ms": timings.fusion_ms,
        "reranker_ms": timings.reranker_ms,
        "postgres_hydration_ms": timings.postgres_hydration_ms,
        "status": "COMPLETED",
    }
    await db.execute(
        insert(SearchRun).values(**values).on_conflict_do_nothing(index_elements=["request_id"])
    )
    if user is not None:
        await db.execute(
            insert(SearchHistory)
            .values(
                request_id=request_id,
                user_id=user.id,
                query=query,
                view=SearchView.DOCUMENTS,
                mode=mode,
                filters=filters.json(),
                sort=filters.sort,
                page_size=page_size,
                result_count=result_count,
                took_ms=timings.total_ms,
            )
            .on_conflict_do_nothing(index_elements=["request_id"])
        )
    await db.flush()


def _milliseconds(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))
