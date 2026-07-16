from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import DB
from app.api.errors import error_response

router = APIRouter(prefix="/health", tags=["health"])


@router.get(
    "/live",
    summary="Проверить процесс API",
    operation_id="healthLive",
)
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get(
    "/ready",
    response_model=None,
    summary="Проверить готовность PostgreSQL",
    operation_id="healthReady",
)
async def ready(request: Request, db: DB) -> dict[str, str] | JSONResponse:
    try:
        await db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return error_response(
            request,
            503,
            "SERVICE_UNAVAILABLE",
            "PostgreSQL недоступен",
        )
    return {"status": "ready"}
