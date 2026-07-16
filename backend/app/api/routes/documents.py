from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from app.api.dependencies import DB, OptionalUser
from app.schemas.content import DocumentOut
from app.services.content import get_public_document

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get(
    "/{document_id}",
    response_model=DocumentOut,
    summary="Получить публичное представление документа",
    operation_id="getDocument",
)
async def document(document_id: UUID, db: DB, user: OptionalUser) -> DocumentOut:
    return await get_public_document(db, document_id, user)
