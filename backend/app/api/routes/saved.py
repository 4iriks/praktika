from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, Response

from app.api.dependencies import DB, CurrentUser
from app.schemas.content import SavedDocumentOut, SavedDocumentsResponse
from app.services.user import get_saved_documents, save_document, unsave_document

router = APIRouter(prefix="/saved", tags=["saved"])


@router.get(
    "",
    response_model=SavedDocumentsResponse,
    summary="Получить сохранённые документы",
    operation_id="getSavedDocuments",
)
async def saved_list(
    db: DB,
    user: CurrentUser,
    search: str = "",
    tags: str = "",
    sort: str = "savedAt",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> SavedDocumentsResponse:
    return await get_saved_documents(
        db,
        user,
        search=search,
        tags=[item for item in tags.split(",") if item],
        sort=sort,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/{document_id}",
    response_model=SavedDocumentOut,
    summary="Сохранить документ",
    operation_id="saveDocument",
)
async def save(document_id: UUID, db: DB, user: CurrentUser) -> SavedDocumentOut:
    return await save_document(db, user, document_id)


@router.delete(
    "/{document_id}",
    status_code=204,
    summary="Удалить документ из сохранённых",
    operation_id="unsaveDocument",
)
async def unsave(document_id: UUID, db: DB, user: CurrentUser) -> Response:
    await unsave_document(db, user, document_id)
    return Response(status_code=204)
