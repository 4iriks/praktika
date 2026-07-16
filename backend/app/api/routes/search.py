from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import Field

from app.api.dependencies import DB, OptionalUser
from app.api.errors import ApiException
from app.core.config import get_settings
from app.core.enums import Permission, SearchMode
from app.schemas.base import ApiModel
from app.schemas.search import SearchResponseOut
from app.services.search import SearchFilters, search_documents
from app.services.system import get_settings_record

router = APIRouter(tags=["search"])


class AskPlaceholderRequest(ApiModel):
    question: str = Field(min_length=1, max_length=4000)
    mode: SearchMode
    max_sources: int | None = Field(default=None, ge=1, le=20)
    document_id: str | None = None
    filters: dict[str, object] | None = None
    page_size: int | None = None


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
    summary="RAG (будет реализован на Этапе 6)",
    operation_id="askQuestion",
    responses={501: {"description": "RAG engine is not configured"}},
)
async def ask_placeholder(payload: AskPlaceholderRequest, db: DB, user: OptionalUser) -> None:
    settings = await get_settings_record(db)
    if user is None and not settings.allow_guest_rag:
        raise ApiException(401, "UNAUTHORIZED", "Для ответа ИИ требуется авторизация")
    raise ApiException(501, "RAG_ENGINE_NOT_READY", "RAG будет подключён на Этапе 6")
