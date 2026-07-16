from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from app.api.dependencies import DB, OptionalUser
from app.api.errors import ApiException
from app.core.config import get_settings
from app.core.enums import Permission, SearchMode
from app.db.models.identity import User
from app.schemas.rag import AskRequest, AskResponseOut
from app.schemas.search import SearchResponseOut
from app.services.rag import ask_question, stream_question
from app.services.search import SearchFilters, search_documents

router = APIRouter(tags=["search"])


@router.get(
    "/search",
    summary="Гибридный поиск по корпусу PyAnswer",
    operation_id="searchDocuments",
    response_model=SearchResponseOut,
    responses={
        401: {"description": "Guest search is disabled"},
        422: {"description": "Invalid query or filters"},
        429: {"description": "Search rate limit exceeded"},
        503: {"description": "Qdrant, embeddings or required reranker unavailable"},
    },
)
async def search(
    request: Request,
    db: DB,
    user: OptionalUser,
    q: str = Query(min_length=1, max_length=10000),
    view: Literal["documents"] = "documents",
    mode: SearchMode = SearchMode.HYBRID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    tags: str = Query(default="", max_length=1000),
    sort: Literal["relevance", "date", "score"] = "relevance",
    min_score: int | None = None,
    accepted: bool = False,
    has_code: bool = False,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    source_id: UUID | None = None,
    section_type: Literal["QUESTION", "ACCEPTED_ANSWER", "ANSWER", "MIXED"] | None = None,
    rerank: bool = True,
) -> SearchResponseOut:
    config = get_settings()
    if page_size > config.search_max_limit:
        raise ApiException(422, "VALIDATION_ERROR", "Превышен максимальный размер страницы")
    if date_from is not None and date_to is not None and date_from > date_to:
        raise ApiException(422, "VALIDATION_ERROR", "dateFrom не может быть позже dateTo")
    parsed_tags = sorted({item.strip().casefold() for item in tags.split(",") if item.strip()})
    if len(parsed_tags) > 20:
        raise ApiException(422, "VALIDATION_ERROR", "Разрешено не более 20 тегов")
    if user is not None:
        permissions = {item.code for item in user.role.permissions}
        if Permission.SEARCH_USE not in permissions:
            raise ApiException(403, "FORBIDDEN", "Недостаточно прав для поиска")
    request_id = str(
        request.headers.get("X-Client-Request-ID")
        or getattr(request.state, "request_id", "unknown")
    )
    return await search_documents(
        db,
        config=config,
        user=user,
        request_id=request_id,
        client_key=request.client.host if request.client else "unknown",
        query=q,
        view=view,
        mode=mode,
        page=page,
        page_size=page_size,
        apply_reranker=rerank,
        filters=SearchFilters(
            tags=parsed_tags,
            date_from=date_from,
            date_to=date_to,
            min_question_score=min_score,
            accepted_only=accepted,
            has_code=has_code,
            source_id=source_id,
            section_type=section_type,
            sort=sort,
        ),
    )


@router.post(
    "/ask",
    summary="Получить локальный RAG-ответ",
    operation_id="askQuestion",
    response_model=AskResponseOut,
    responses={
        401: {"description": "Guest RAG is disabled"},
        403: {"description": "Missing RAG permission or CSRF token"},
        409: {"description": "Duplicate request is still running or terminally failed"},
        429: {"description": "RAG rate limit exceeded"},
        503: {"description": "Search, reranker or local LLM unavailable"},
        504: {"description": "Local LLM timeout"},
    },
)
async def ask(
    payload: AskRequest,
    request: Request,
    db: DB,
    user: OptionalUser,
) -> AskResponseOut:
    _require_rag_permission(user)
    request_id = str(
        payload.client_request_id
        or request.headers.get("X-Client-Request-ID")
        or getattr(request.state, "request_id", "unknown")
    )
    return await ask_question(
        db,
        config=get_settings(),
        user=user,
        request_id=request_id,
        client_key=request.client.host if request.client else "unknown",
        payload=payload,
    )


@router.post(
    "/ask/stream",
    summary="Потоковый локальный RAG-ответ",
    operation_id="streamAnswer",
    response_class=StreamingResponse,
    responses={
        200: {"description": "SSE events: started/status/sources/token/metrics/done/error"},
        403: {"description": "Missing RAG permission or CSRF token"},
    },
)
async def ask_stream(
    payload: AskRequest,
    request: Request,
    db: DB,
    user: OptionalUser,
) -> StreamingResponse:
    _require_rag_permission(user)
    request_id = str(
        payload.client_request_id
        or request.headers.get("X-Client-Request-ID")
        or getattr(request.state, "request_id", "unknown")
    )

    async def events() -> AsyncIterator[str]:
        async for event, data in stream_question(
            db,
            config=get_settings(),
            user=user,
            request_id=request_id,
            client_key=request.client.host if request.client else "unknown",
            payload=payload,
            disconnected=request.is_disconnected,
        ):
            yield _sse(event, data)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _require_rag_permission(user: User | None) -> None:
    if user is None:
        return
    permissions = {item.code for item in user.role.permissions}
    if Permission.RAG_USE not in permissions:
        raise ApiException(403, "FORBIDDEN", "Недостаточно прав для RAG")


def _sse(event: str, data: dict[str, object]) -> str:
    return (
        f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"
    )
