from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import DB, require_permission
from app.core.enums import Permission
from app.db.models.identity import User
from app.schemas.management import BackgroundJobOut
from app.schemas.search_index import (
    CleanupIndexesRequest,
    FullReindexRequest,
    SearchIndexStatsOut,
    SearchIndexVersionOut,
    SearchIndexVersionsResponse,
    ValidateIndexRequest,
)
from app.services.admin_indexes import (
    enqueue_cleanup,
    enqueue_full_reindex,
    enqueue_validation,
    get_active_index,
    get_index_stats,
    get_index_version,
    list_index_versions,
)

router = APIRouter(prefix="/admin/indexes", tags=["admin-indexes"])
IndexViewer = Annotated[User, Depends(require_permission(Permission.SEARCH_INDEX_VIEW))]
IndexManager = Annotated[User, Depends(require_permission(Permission.SEARCH_INDEX_MANAGE))]


@router.get(
    "",
    response_model=SearchIndexVersionsResponse,
    summary="Получить версии поискового индекса",
    operation_id="getSearchIndexes",
)
async def indexes(
    db: DB,
    actor: IndexViewer,
    status: str = "ALL",
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> SearchIndexVersionsResponse:
    return await list_index_versions(db, status=status, page=page, limit=limit)


@router.get(
    "/active",
    response_model=SearchIndexVersionOut | None,
    summary="Получить активную версию индекса",
    operation_id="getActiveSearchIndex",
)
async def active(db: DB, actor: IndexViewer) -> SearchIndexVersionOut | None:
    return await get_active_index(db)


@router.get(
    "/stats",
    response_model=SearchIndexStatsOut,
    summary="Получить метрики поискового индекса",
    operation_id="getSearchIndexStats",
)
async def stats(db: DB, actor: IndexViewer) -> SearchIndexStatsOut:
    return await get_index_stats(db)


@router.post(
    "/full-reindex",
    response_model=BackgroundJobOut,
    summary="Запустить blue-green полную переиндексацию",
    operation_id="startSearchIndexFullReindex",
)
async def full_reindex(
    payload: FullReindexRequest,
    request: Request,
    db: DB,
    actor: IndexManager,
) -> BackgroundJobOut:
    return await enqueue_full_reindex(db, request, actor, payload)


@router.post(
    "/cleanup",
    response_model=BackgroundJobOut,
    summary="Проверить или очистить устаревшие collections",
    operation_id="cleanupSearchIndexes",
)
async def cleanup(
    payload: CleanupIndexesRequest,
    request: Request,
    db: DB,
    actor: IndexManager,
) -> BackgroundJobOut:
    return await enqueue_cleanup(db, request, actor, payload)


@router.get(
    "/{index_version_id}",
    response_model=SearchIndexVersionOut,
    summary="Получить версию поискового индекса",
    operation_id="getSearchIndex",
)
async def detail(index_version_id: UUID, db: DB, actor: IndexViewer) -> SearchIndexVersionOut:
    return await get_index_version(db, index_version_id)


@router.post(
    "/{index_version_id}/validate",
    response_model=BackgroundJobOut,
    summary="Проверить версию поискового индекса",
    operation_id="validateSearchIndex",
)
async def validate(
    index_version_id: UUID,
    payload: ValidateIndexRequest,
    request: Request,
    db: DB,
    actor: IndexManager,
) -> BackgroundJobOut:
    return await enqueue_validation(db, request, actor, index_version_id, payload)
