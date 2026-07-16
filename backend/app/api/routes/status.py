from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.dependencies import DB
from app.db.base import utc_now
from app.db.models.content import Document
from app.schemas.content import (
    PublicAccessPolicyOut,
    PublicServiceStatusOut,
    PublicSystemStatusOut,
)
from app.services.system import public_policy

router = APIRouter(tags=["status"])


@router.get(
    "/status",
    response_model=PublicSystemStatusOut,
    summary="Получить публичное состояние",
    operation_id="getPublicSystemStatus",
)
async def public_status(db: DB) -> PublicSystemStatusOut:
    documents = await db.scalar(select(func.count()).select_from(Document)) or 0
    chunks = await db.scalar(select(func.coalesce(func.sum(Document.chunks_count), 0))) or 0
    return PublicSystemStatusOut(
        services=[
            PublicServiceStatusOut(name="API", state="online"),
            PublicServiceStatusOut(name="PostgreSQL", state="online"),
            PublicServiceStatusOut(name="Qdrant", state="offline"),
            PublicServiceStatusOut(name="Ollama", state="offline"),
            PublicServiceStatusOut(name="Index", state="offline"),
        ],
        model="Не подключена",
        model_context=0,
        indexed_documents=documents,
        indexed_chunks=chunks,
        updated_at=utc_now(),
    )


@router.get(
    "/system/public-policy",
    response_model=PublicAccessPolicyOut,
    summary="Получить публичную политику доступа",
    operation_id="getPublicAccessPolicy",
)
async def policy(db: DB) -> PublicAccessPolicyOut:
    return await public_policy(db)
