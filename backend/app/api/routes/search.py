from __future__ import annotations

from fastapi import APIRouter
from pydantic import Field

from app.api.dependencies import DB, OptionalUser
from app.api.errors import ApiException
from app.core.enums import SearchMode
from app.schemas.base import ApiModel
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
    summary="Поиск (будет реализован на Этапе 6)",
    operation_id="searchDocuments",
    responses={501: {"description": "Search engine is not configured"}},
)
async def search_placeholder(db: DB, user: OptionalUser, q: str = "") -> None:
    settings = await get_settings_record(db)
    if user is None and not settings.allow_guest_search:
        raise ApiException(401, "UNAUTHORIZED", "Для поиска требуется авторизация")
    raise ApiException(
        501, "SEARCH_ENGINE_NOT_READY", "Поисковый движок будет подключён на Этапе 6"
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
