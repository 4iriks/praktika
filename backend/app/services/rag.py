from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.errors import ApiException
from app.core.config import Settings
from app.core.enums import (
    ConfidenceLabel,
    DeduplicationStatus,
    DocumentStatus,
    ProcessingStatus,
    RagResponseStatus,
    SearchView,
)
from app.core.rate_limit import InMemoryRateLimiter
from app.db.base import utc_now
from app.db.models.content import Document, DocumentChunk, DocumentTag
from app.db.models.identity import SavedDocument, SearchHistory, User
from app.db.models.operations import (
    RagResponse,
    RagResponseSource,
    SearchIndexVersion,
)
from app.integrations.llm import (
    LlmProvider,
    LlmProviderError,
    LlmResult,
    OllamaLlmProvider,
)
from app.integrations.llm.gate import InferenceGate
from app.rag import (
    BuiltContext,
    ContextBuilder,
    RetrievedPassage,
    calculate_confidence,
    prompt_hash,
    prompt_messages,
    validate_citations,
)
from app.schemas.content import TagOut
from app.schemas.rag import AskRequest, AskResponseOut, RagDiagnosticsOut, RagSourceOut
from app.schemas.search import SearchResultOut
from app.services.content import selected_tags
from app.services.search import SearchFilters, search_documents
from app.services.system import get_settings_record

INSUFFICIENT_ANSWER = (
    "В базе не найдено достаточно информации для надёжного ответа. Попробуйте уточнить запрос."
)


@dataclass(slots=True)
class RagPreparation:
    row: RagResponse
    context: BuiltContext
    query: str
    index_version: str
    existing_response: AskResponseOut | None = None


_gate: InferenceGate | None = None
_gate_config: tuple[int, int, float] | None = None
_rate_limiters: dict[tuple[int, int, bool], InMemoryRateLimiter] = {}


def get_llm_gate(config: Settings) -> InferenceGate:
    global _gate, _gate_config
    current = (
        config.llm_max_concurrent_requests,
        config.llm_queue_limit,
        config.llm_queue_timeout_seconds,
    )
    if _gate is None or _gate_config != current:
        _gate = InferenceGate(*current)
        _gate_config = current
    return _gate


async def rag_diagnostics(db: AsyncSession, config: Settings) -> RagDiagnosticsOut:
    provider = OllamaLlmProvider(config)
    try:
        health = await provider.health()
    finally:
        await provider.close()
    snapshot = get_llm_gate(config).snapshot()
    active_index = await db.scalar(
        select(SearchIndexVersion.schema_hash).where(SearchIndexVersion.status == "ACTIVE")
    )
    total = await db.scalar(select(func.count()).select_from(RagResponse)) or 0
    failures = (
        await db.scalar(
            select(func.count())
            .select_from(RagResponse)
            .where(RagResponse.status == RagResponseStatus.FAILED)
        )
        or 0
    )
    insufficient = (
        await db.scalar(
            select(func.count())
            .select_from(RagResponse)
            .where(RagResponse.insufficient_context.is_(True))
        )
        or 0
    )
    citations_ok = (
        await db.scalar(
            select(func.count())
            .select_from(RagResponse)
            .where(
                RagResponse.status == RagResponseStatus.COMPLETED,
                RagResponse.citation_validation_passed.is_(True),
            )
        )
        or 0
    )
    average = await db.scalar(
        select(func.avg(RagResponse.generation_ms)).where(
            RagResponse.status == RagResponseStatus.COMPLETED
        )
    )
    return RagDiagnosticsOut(
        provider=config.llm_provider,
        model=config.llm_model,
        model_installed=health.model_installed,
        model_loaded=health.model_loaded,
        online=health.online,
        context_tokens=config.llm_num_ctx,
        queue_active=snapshot.active,
        queue_waiting=snapshot.waiting,
        queue_limit=snapshot.queue_limit,
        prompt_version=config.rag_prompt_version,
        active_index=active_index,
        recent_failures=failures,
        insufficient_context_rate=round(insufficient / total, 3) if total else 0,
        citation_validation_rate=round(citations_ok / total, 3) if total else 0,
        average_generation_ms=round(float(average or 0)),
        checked_at=utc_now(),
    )


async def ask_question(
    db: AsyncSession,
    *,
    config: Settings,
    user: User | None,
    request_id: str,
    client_key: str,
    payload: AskRequest,
    llm: LlmProvider | None = None,
) -> AskResponseOut:
    started = time.perf_counter()
    prepared = await prepare_rag(
        db,
        config=config,
        user=user,
        request_id=request_id,
        client_key=client_key,
        payload=payload,
    )
    if prepared.existing_response is not None:
        return prepared.existing_response
    own_llm = llm is None
    provider: LlmProvider = llm if llm is not None else OllamaLlmProvider(config)
    try:
        async with get_llm_gate(config).slot():
            mark = time.perf_counter()
            result = await provider.chat(prompt_messages(prepared.query, prepared.context.text))
            generation_ms = _milliseconds(mark)
        return await _complete(
            db,
            config=config,
            prepared=prepared,
            result=result,
            generation_ms=generation_ms,
            total_ms=_milliseconds(started),
        )
    except LlmProviderError as exc:
        await _mark_terminal(db, prepared.row, RagResponseStatus.FAILED, exc.code)
        raise _llm_api_error(exc) from exc
    except asyncio.CancelledError:
        await _mark_terminal(db, prepared.row, RagResponseStatus.CANCELLED, "CLIENT_CANCELLED")
        raise
    finally:
        if own_llm:
            await provider.close()


async def stream_question(
    db: AsyncSession,
    *,
    config: Settings,
    user: User | None,
    request_id: str,
    client_key: str,
    payload: AskRequest,
    disconnected: Callable[[], Awaitable[bool]],
    llm: LlmProvider | None = None,
) -> AsyncIterator[tuple[str, dict[str, object]]]:
    started = time.perf_counter()
    yield "started", {"requestId": request_id}
    yield "status", {"stage": "validating"}
    try:
        yield "status", {"stage": "searching"}
        prepared = await prepare_rag(
            db,
            config=config,
            user=user,
            request_id=request_id,
            client_key=client_key,
            payload=payload,
        )
    except ApiException as exc:
        yield "error", {"code": exc.code, "message": exc.message}
        return
    yield "status", {"stage": "fusing"}
    yield "status", {"stage": "reranking"}
    yield "status", {"stage": "selecting_sources"}
    response = prepared.existing_response
    if response is not None:
        yield "sources", {"sources": _json_sources(response.sources)}
        if response.answer:
            yield "token", {"content": response.answer}
        yield "metrics", _response_metrics(response)
        yield "done", response.model_dump(mode="json", by_alias=True)
        return
    sources = await _source_schemas(db, prepared.row)
    yield "sources", {"sources": _json_sources(sources)}
    yield "heartbeat", {"stage": "generating"}
    yield "status", {"stage": "generating"}
    own_llm = llm is None
    provider: LlmProvider = llm if llm is not None else OllamaLlmProvider(config)
    chunks: list[str] = []
    final_event = None
    generation_started = time.perf_counter()
    try:
        async with get_llm_gate(config).slot():
            async for event in provider.stream_chat(
                prompt_messages(prepared.query, prepared.context.text)
            ):
                if await disconnected():
                    raise asyncio.CancelledError
                if event.content:
                    chunks.append(event.content)
                    yield "token", {"content": event.content}
                if event.done:
                    final_event = event
        if final_event is None:
            raise LlmProviderError("LLM_STREAM_INCOMPLETE", "Ollama не завершила ответ")
        yield "status", {"stage": "validating_citations"}
        result = LlmResult(
            content="".join(chunks),
            model=final_event.model or provider.model_name,
            model_version=final_event.model_version,
            prompt_tokens=final_event.prompt_tokens,
            output_tokens=final_event.output_tokens,
            total_duration_ns=final_event.total_duration_ns,
        )
        yield "status", {"stage": "saving"}
        response = await _complete(
            db,
            config=config,
            prepared=prepared,
            result=result,
            generation_ms=_milliseconds(generation_started),
            total_ms=_milliseconds(started),
        )
        yield "metrics", _response_metrics(response)
        yield "status", {"stage": "completed"}
        yield "done", response.model_dump(mode="json", by_alias=True)
    except LlmProviderError as exc:
        await _mark_terminal(db, prepared.row, RagResponseStatus.FAILED, exc.code)
        api_error = _llm_api_error(exc)
        yield "error", {"code": api_error.code, "message": api_error.message}
    except asyncio.CancelledError:
        await _mark_terminal(db, prepared.row, RagResponseStatus.CANCELLED, "CLIENT_CANCELLED")
        return
    finally:
        if own_llm:
            await provider.close()


async def prepare_rag(
    db: AsyncSession,
    *,
    config: Settings,
    user: User | None,
    request_id: str,
    client_key: str,
    payload: AskRequest,
) -> RagPreparation:
    request_id = (payload.client_request_id or request_id)[:80]
    existing = await db.scalar(select(RagResponse).where(RagResponse.request_id == request_id))
    if existing is not None:
        if existing.status == RagResponseStatus.COMPLETED:
            return RagPreparation(
                row=existing,
                context=BuiltContext("", (), 0),
                query=existing.query,
                index_version=await _index_hash(db, existing.index_version_id),
                existing_response=await _response_schema(db, existing),
            )
        raise ApiException(409, "CONFLICT", "Запрос с таким clientRequestId уже выполнялся")
    system = await get_settings_record(db)
    if user is None and not system.allow_guest_rag:
        raise ApiException(401, "UNAUTHORIZED", "Для ответа ИИ требуется авторизация")
    _check_rate_limit(config, user, client_key)
    maximum_sources = min(
        payload.max_sources or system.rag_sources_limit,
        system.rag_sources_limit,
        config.rag_sources_limit,
        config.rag_max_source_count,
    )
    search_started = time.perf_counter()
    search_response = await search_documents(
        db,
        config=config,
        user=user,
        request_id="rag-search-" + hashlib.sha256(request_id.encode()).hexdigest()[:50],
        client_key=client_key,
        query=payload.question,
        view=SearchView.DOCUMENTS,
        mode=payload.mode,
        page=1,
        page_size=maximum_sources,
        apply_reranker=True,
        persist_history=False,
        filters=SearchFilters(
            tags=payload.filters.tags,
            date_from=None,
            date_to=None,
            min_question_score=payload.filters.min_score,
            accepted_only=payload.filters.accepted_only,
            has_code=payload.filters.has_code_only,
            source_id=None,
            section_type=None,
            sort=payload.filters.sort,
        ),
    )
    search_ms = _milliseconds(search_started)
    if (
        config.rag_reranker_required
        and search_response.results
        and not search_response.metrics.reranker_applied
    ):
        raise ApiException(503, "SERVICE_UNAVAILABLE", "Reranker обязателен для RAG")
    passages = await _load_passages(
        db,
        search_response.results,
        document_id=payload.document_id,
        max_chunks_per_document=config.rag_max_chunks_per_document,
    )
    context = ContextBuilder(
        token_budget=config.rag_context_token_budget,
        max_sources=maximum_sources,
        max_chunks_per_document=config.rag_max_chunks_per_document,
    ).build(passages)
    top_reranker = max((source.reranker_score or 0 for source in context.sources), default=0)
    insufficient = (
        len(context.sources) < config.rag_min_source_count
        or context.token_count < config.rag_min_context_tokens
        or top_reranker < config.rag_min_reranker_score
    )
    index_version = search_response.metrics.index_version
    index_id = await db.scalar(
        select(SearchIndexVersion.id).where(SearchIndexVersion.schema_hash == index_version)
    )
    row = RagResponse(
        request_id=request_id,
        user_id=user.id if user else None,
        query=payload.question.strip(),
        search_mode=payload.mode,
        answer_text=INSUFFICIENT_ANSWER if insufficient else "",
        model=config.llm_model,
        prompt_version=config.rag_prompt_version,
        prompt_hash=prompt_hash(config.rag_prompt_version),
        index_version_id=index_id,
        confidence=0.1 if insufficient else 0,
        confidence_label=ConfidenceLabel.LOW,
        insufficient_context=insufficient,
        citation_validation_passed=insufficient,
        source_count=len(context.sources),
        search_ms=search_ms,
        reranker_ms=search_response.metrics.timings.reranker_ms,
        generation_ms=0,
        total_ms=search_ms if insufficient else 0,
        prompt_tokens=context.token_count,
        status=RagResponseStatus.COMPLETED if insufficient else RagResponseStatus.GENERATING,
    )
    db.add(row)
    await db.flush()
    for source in context.sources:
        db.add(
            RagResponseSource(
                response_id=row.id,
                chunk_id=source.chunk_id,
                document_id=source.document_id,
                citation_index=source.citation_index,
                rank=source.rank,
                bm25_score=source.bm25_score,
                vector_score=source.vector_score,
                fusion_score=source.fusion_score,
                reranker_score=source.reranker_score,
                source_url=source.source_url,
                title=source.title,
                passage_hash=source.passage_hash,
            )
        )
    if insufficient:
        await _persist_rag_history(db, row)
    await db.commit()  # No transaction is held while Ollama generates tokens.
    prepared = RagPreparation(
        row=row, context=context, query=row.query, index_version=index_version
    )
    if insufficient:
        prepared.existing_response = await _response_schema(db, row)
    return prepared


async def _complete(
    db: AsyncSession,
    *,
    config: Settings,
    prepared: RagPreparation,
    result: LlmResult,
    generation_ms: int,
    total_ms: int,
) -> AskResponseOut:
    validation = validate_citations(result.content, len(prepared.context.sources))
    citation_passed = validation.valid and bool(validation.cited_indexes)
    confidence = calculate_confidence(
        prepared.context.sources,
        validation.cited_indexes,
        insufficient=False,
    )
    row = await db.get(RagResponse, prepared.row.id, with_for_update=True)
    if row is None:
        raise ApiException(500, "INTERNAL_ERROR", "RAG response потерян")
    row.answer_text = validation.answer
    row.model = result.model
    row.model_version = result.model_version
    row.confidence = confidence.value
    row.confidence_label = confidence.label
    row.citation_validation_passed = citation_passed
    row.generation_ms = generation_ms
    row.total_ms = total_ms
    row.prompt_tokens = result.prompt_tokens or prepared.context.token_count
    row.output_tokens = result.output_tokens
    row.status = RagResponseStatus.COMPLETED
    await _persist_rag_history(db, row)
    await db.commit()
    return await _response_schema(db, row, confidence_formula=confidence.formula_version)


async def _mark_terminal(
    db: AsyncSession, row: RagResponse, status: RagResponseStatus, error_code: str
) -> None:
    current = await db.get(RagResponse, row.id, with_for_update=True)
    if current is not None and current.status == RagResponseStatus.GENERATING:
        current.status = status
        current.error_code = error_code[:80]
        await db.commit()


async def _persist_rag_history(db: AsyncSession, row: RagResponse) -> None:
    if row.user_id is None:
        return
    await db.execute(
        insert(SearchHistory)
        .values(
            request_id=row.request_id,
            response_id=row.id,
            user_id=row.user_id,
            query=row.query,
            view=SearchView.ANSWER,
            mode=row.search_mode,
            filters={},
            sort="relevance",
            page_size=max(1, row.source_count),
            result_count=row.source_count,
            took_ms=row.total_ms,
            answer_preview=row.answer_text[:1000],
            insufficient_context=row.insufficient_context,
        )
        .on_conflict_do_nothing(index_elements=["request_id"])
    )


async def _load_passages(
    db: AsyncSession,
    results: Sequence[SearchResultOut],
    *,
    document_id: UUID | None,
    max_chunks_per_document: int,
) -> list[RetrievedPassage]:
    ids: list[UUID] = []
    by_result: list[tuple[SearchResultOut, list[UUID]]] = []
    for result in results:
        if document_id is not None and UUID(result.document_id) != document_id:
            continue
        selected: list[UUID] = []
        for raw in [result.chunk_id, *(item.chunk_id for item in result.matched_chunks)]:
            chunk_id = UUID(raw)
            if chunk_id not in selected:
                selected.append(chunk_id)
            if len(selected) >= max_chunks_per_document:
                break
        ids.extend(selected)
        by_result.append((result, selected))
    chunks = (
        await db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.id.in_(ids))
            .options(
                selectinload(DocumentChunk.document).selectinload(Document.source),
                selectinload(DocumentChunk.document)
                .selectinload(Document.tag_links)
                .selectinload(DocumentTag.tag),
            )
        )
    ).all()
    chunk_map = {chunk.id: chunk for chunk in chunks}
    passages: list[RetrievedPassage] = []
    for result, chunk_ids in by_result:
        for chunk_id in chunk_ids:
            chunk = chunk_map.get(chunk_id)
            if chunk is None or not _rag_visible(chunk) or not _trusted_source(chunk.document):
                continue
            passages.append(
                RetrievedPassage(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    title=result.title,
                    source_url=result.source_url,
                    tags=tuple(tag.slug for tag in result.tags),
                    section_type=chunk.section_type,
                    text=chunk.text,
                    rank=result.rank,
                    bm25_score=result.bm25_score,
                    vector_score=result.vector_score,
                    fusion_score=result.fusion_score,
                    reranker_score=result.reranker_score,
                    final_score=result.final_score,
                    saved=result.saved,
                )
            )
    return passages


def _rag_visible(chunk: DocumentChunk) -> bool:
    document = chunk.document
    return (
        document.status in {DocumentStatus.ACTIVE, DocumentStatus.OUTDATED}
        and document.processing_status == ProcessingStatus.CHUNKED
        and document.deduplication_status == DeduplicationStatus.UNIQUE
        and chunk.document_version == document.version
        and not document.processing_error
    )


def _trusted_source(document: Document) -> bool:
    source_host = urlparse(document.source.base_url).hostname
    document_host = urlparse(document.source_url).hostname
    return bool(
        document_host and source_host and document_host.casefold() == source_host.casefold()
    )


async def _response_schema(
    db: AsyncSession, row: RagResponse, *, confidence_formula: str = "retrieval-v1"
) -> AskResponseOut:
    return AskResponseOut(
        response_id=row.id,
        answer=row.answer_text,
        sources=await _source_schemas(db, row),
        model=row.model,
        model_version=row.model_version,
        took_ms=row.total_ms,
        search_took_ms=row.search_ms,
        reranker_took_ms=row.reranker_ms,
        generation_took_ms=row.generation_ms,
        confidence=row.confidence,
        confidence_label=row.confidence_label,
        confidence_formula_version=confidence_formula,
        insufficient_context=row.insufficient_context,
        citation_validation_passed=row.citation_validation_passed,
        index_version=await _index_hash(db, row.index_version_id),
        prompt_version=row.prompt_version,
    )


async def _source_schemas(db: AsyncSession, row: RagResponse) -> list[RagSourceOut]:
    records = (
        await db.scalars(
            select(RagResponseSource)
            .where(RagResponseSource.response_id == row.id)
            .order_by(RagResponseSource.citation_index)
        )
    ).all()
    chunk_ids = [record.chunk_id for record in records]
    chunks = (
        await db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.id.in_(chunk_ids))
            .options(
                selectinload(DocumentChunk.document)
                .selectinload(Document.tag_links)
                .selectinload(DocumentTag.tag)
            )
        )
    ).all()
    by_id = {chunk.id: chunk for chunk in chunks}
    saved_ids: set[UUID] = set()
    if row.user_id is not None:
        saved_ids = set(
            await db.scalars(
                select(SavedDocument.document_id).where(
                    SavedDocument.user_id == row.user_id,
                    SavedDocument.document_id.in_([record.document_id for record in records]),
                )
            )
        )
    output: list[RagSourceOut] = []
    for record in records:
        chunk = by_id.get(record.chunk_id)
        if chunk is None:
            continue
        output.append(
            RagSourceOut(
                citation_index=record.citation_index,
                chunk_id=record.chunk_id,
                document_id=record.document_id,
                title=record.title,
                snippet=chunk.text[:700],
                source_url=record.source_url,
                tags=[
                    TagOut(name=tag.display_name, slug=tag.normalized_name)
                    for tag in selected_tags(chunk.document)
                ],
                section_type=chunk.section_type,
                score=record.reranker_score or record.fusion_score,
                bm25_score=record.bm25_score,
                vector_score=record.vector_score,
                fusion_score=record.fusion_score,
                reranker_score=record.reranker_score,
                saved=record.document_id in saved_ids,
            )
        )
    return output


async def _index_hash(db: AsyncSession, index_id: UUID | None) -> str:
    if index_id is None:
        return "unknown"
    return (
        await db.scalar(
            select(SearchIndexVersion.schema_hash).where(SearchIndexVersion.id == index_id)
        )
        or "unknown"
    )


def _check_rate_limit(config: Settings, user: User | None, client_key: str) -> None:
    authenticated = user is not None
    limit = (
        config.rag_authenticated_rate_limit_requests
        if authenticated
        else config.rag_guest_rate_limit_requests
    )
    key = (limit, config.rag_rate_limit_window_seconds, authenticated)
    limiter = _rate_limiters.setdefault(
        key,
        InMemoryRateLimiter(limit=limit, window_seconds=config.rag_rate_limit_window_seconds),
    )
    limiter.check(("user:" + str(user.id)) if user else ("guest:" + client_key))


def _llm_api_error(error: LlmProviderError) -> ApiException:
    if error.code == "LLM_TIMEOUT":
        return ApiException(504, "GATEWAY_TIMEOUT", error.safe_message)
    return ApiException(503, "SERVICE_UNAVAILABLE", error.safe_message)


def _response_metrics(response: AskResponseOut) -> dict[str, object]:
    return {
        "tookMs": response.took_ms,
        "searchTookMs": response.search_took_ms,
        "rerankerTookMs": response.reranker_took_ms,
        "generationTookMs": response.generation_took_ms,
        "confidence": response.confidence,
    }


def _json_sources(sources: list[RagSourceOut]) -> list[dict[str, object]]:
    return [source.model_dump(mode="json", by_alias=True) for source in sources]


def _milliseconds(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))
