from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import DB, require_permission
from app.api.pagination import parse_optional_datetime
from app.core.enums import Permission
from app.db.models.identity import User
from app.schemas.ingestion import JobEventsResponse
from app.schemas.management import BackgroundJobOut, JobsResponse
from app.services.admin_jobs import (
    cancel_job,
    get_job_record,
    retry_job,
    start_full_reindex,
)
from app.services.editor import list_jobs
from app.services.ingestion import list_job_events
from app.services.management_serializers import job_to_schema

router = APIRouter(prefix="/admin/jobs", tags=["admin-jobs"])
JobsAdmin = Annotated[User, Depends(require_permission(Permission.ADMIN_JOBS_MANAGE))]


@router.get(
    "",
    response_model=JobsResponse,
    summary="Получить все фоновые задания",
    operation_id="getAdminJobs",
)
async def jobs(
    db: DB,
    actor: JobsAdmin,
    id: str = "",
    type: str = "ALL",
    status: str = "ALL",
    stage: str = "ALL",
    actor_filter: str = Query("", alias="actor"),
    document_id: str = "",
    source: str = "",
    date_from: str = "",
    date_to: str = "",
    sort: str = "created_desc",
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> JobsResponse:
    return await list_jobs(
        db,
        job_id=id,
        type_filter=type,
        status=status,
        stage=stage,
        actor=actor_filter,
        document_id=document_id,
        source=source,
        date_from=parse_optional_datetime(date_from),
        date_to=parse_optional_datetime(date_to),
        sort=sort,
        page=page,
        limit=limit,
    )


@router.post(
    "/full-reindex",
    response_model=BackgroundJobOut,
    summary="Создать полную переиндексацию",
    operation_id="startFullReindex",
)
async def full_reindex(request: Request, db: DB, actor: JobsAdmin) -> BackgroundJobOut:
    return await start_full_reindex(db, request, actor)


@router.get(
    "/{job_id}/events",
    response_model=JobEventsResponse,
    summary="Получить события фонового задания",
    operation_id="getAdminJobEvents",
)
async def job_events(
    job_id: UUID,
    db: DB,
    actor: JobsAdmin,
    sort: str = "created_asc",
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
) -> JobEventsResponse:
    return await list_job_events(db, job_id, sort=sort, page=page, limit=limit)


@router.get(
    "/{job_id}",
    response_model=BackgroundJobOut,
    summary="Получить фоновое задание",
    operation_id="getAdminJob",
)
async def job_detail(job_id: UUID, db: DB, actor: JobsAdmin) -> BackgroundJobOut:
    return job_to_schema(await get_job_record(db, job_id))


@router.post(
    "/{job_id}/retry",
    response_model=BackgroundJobOut,
    summary="Повторить фоновое задание",
    operation_id="retryJob",
)
async def retry(job_id: UUID, request: Request, db: DB, actor: JobsAdmin) -> BackgroundJobOut:
    return await retry_job(db, request, actor, job_id)


@router.post(
    "/{job_id}/cancel",
    response_model=BackgroundJobOut,
    summary="Отменить фоновое задание",
    operation_id="cancelJob",
)
async def cancel(job_id: UUID, request: Request, db: DB, actor: JobsAdmin) -> BackgroundJobOut:
    return await cancel_job(db, request, actor, job_id)
