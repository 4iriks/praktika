from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import DB, require_permission
from app.core.enums import Permission
from app.db.models.identity import User
from app.schemas.ingestion import (
    IngestionFailureOut,
    IngestionFailuresResponse,
    IngestionStatsOut,
)
from app.services.ingestion import (
    get_ingestion_failure,
    ingestion_stats,
    list_ingestion_failures,
)

router = APIRouter(prefix="/admin/ingestion", tags=["admin-ingestion"])
IngestionAdmin = Annotated[User, Depends(require_permission(Permission.SOURCES_MANAGE))]


@router.get(
    "/stats",
    response_model=IngestionStatsOut,
    summary="Получить статистику ingestion",
    operation_id="getIngestionStats",
)
async def stats(db: DB, actor: IngestionAdmin) -> IngestionStatsOut:
    return await ingestion_stats(db)


@router.get(
    "/failures",
    response_model=IngestionFailuresResponse,
    summary="Получить ошибки ingestion",
    operation_id="getIngestionFailures",
)
async def failures(
    db: DB,
    actor: IngestionAdmin,
    source_id: UUID | None = None,
    job_id: UUID | None = None,
    external_id: str = "",
    error_code: str = "",
    retryable: str = "all",
    resolved: str = "all",
    sort: str = "created_desc",
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> IngestionFailuresResponse:
    return await list_ingestion_failures(
        db,
        source_id=source_id,
        job_id=job_id,
        external_id=external_id,
        error_code=error_code,
        retryable=retryable,
        resolved=resolved,
        sort=sort,
        page=page,
        limit=limit,
    )


@router.get(
    "/failures/{failure_id}",
    response_model=IngestionFailureOut,
    summary="Получить ошибку ingestion",
    operation_id="getIngestionFailure",
)
async def failure_detail(
    failure_id: UUID,
    db: DB,
    actor: IngestionAdmin,
) -> IngestionFailureOut:
    return await get_ingestion_failure(db, failure_id)
