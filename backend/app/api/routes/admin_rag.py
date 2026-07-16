from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import DB, require_permission
from app.core.config import get_settings
from app.core.enums import Permission
from app.db.models.identity import User
from app.schemas.rag import AskRequest, AskResponseOut, RagDiagnosticsOut
from app.services.rag import ask_question, rag_diagnostics

router = APIRouter(prefix="/admin/rag", tags=["admin-rag"])
RagViewer = Annotated[User, Depends(require_permission(Permission.SYSTEM_VIEW))]


@router.get(
    "",
    response_model=RagDiagnosticsOut,
    summary="Получить состояние локального RAG",
    operation_id="getRagDiagnostics",
)
async def diagnostics(db: DB, actor: RagViewer) -> RagDiagnosticsOut:
    return await rag_diagnostics(db, get_settings())


@router.post(
    "/test",
    response_model=AskResponseOut,
    summary="Выполнить диагностический RAG-запрос",
    operation_id="testRag",
)
async def test_rag(
    payload: AskRequest,
    request: Request,
    db: DB,
    actor: RagViewer,
) -> AskResponseOut:
    return await ask_question(
        db,
        config=get_settings(),
        user=actor,
        request_id=str(
            payload.client_request_id or getattr(request.state, "request_id", "admin-rag-test")
        ),
        client_key=request.client.host if request.client else "admin",
        payload=payload,
    )
