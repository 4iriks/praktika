from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, Response

from app.api.dependencies import DB, CurrentUser
from app.api.pagination import parse_optional_datetime
from app.schemas.content import HistoryResponse
from app.services.user import clear_history, delete_history_item, get_history

router = APIRouter(prefix="/history", tags=["history"])


@router.get(
    "",
    response_model=HistoryResponse,
    summary="Получить собственную историю",
    operation_id="getHistory",
)
async def history_list(
    db: DB,
    user: CurrentUser,
    search: str = "",
    view: str = "all",
    mode: str = "all",
    date_sort: str = "newest",
    date_from: str = "",
    date_to: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> HistoryResponse:
    return await get_history(
        db,
        user,
        search=search,
        view=view,
        mode=mode,
        date_sort=date_sort,
        date_from=parse_optional_datetime(date_from),
        date_to=parse_optional_datetime(date_to),
        page=page,
        page_size=page_size,
    )


@router.delete(
    "/{history_id}",
    status_code=204,
    summary="Удалить запись собственной истории",
    operation_id="deleteHistoryItem",
)
async def delete_item(history_id: UUID, db: DB, user: CurrentUser) -> Response:
    await delete_history_item(db, user, history_id)
    return Response(status_code=204)


@router.delete(
    "",
    status_code=204,
    summary="Очистить собственную историю",
    operation_id="clearHistory",
)
async def clear_items(db: DB, user: CurrentUser) -> Response:
    await clear_history(db, user)
    return Response(status_code=204)
