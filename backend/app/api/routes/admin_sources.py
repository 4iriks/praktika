from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import DB, require_permission
from app.core.enums import Permission
from app.db.models.identity import User
from app.schemas.ingestion import SourceSyncRequest, SourceSyncStateOut
from app.schemas.management import (
    BackgroundJobOut,
    SourceConnectionResultOut,
    SourceOut,
    SourcesResponse,
    SourceUpdateRequest,
)
from app.services.admin_sources import (
    get_source_record,
    list_sources,
    start_source_sync,
    stop_source_sync,
    test_source_connection,
    update_source,
)
from app.services.ingestion import get_or_create_sync_state, source_sync_state_to_schema
from app.services.management_serializers import source_to_schema

router = APIRouter(prefix="/admin/sources", tags=["admin-sources"])
SourcesAdmin = Annotated[User, Depends(require_permission(Permission.SOURCES_MANAGE))]


@router.get(
    "",
    response_model=SourcesResponse,
    summary="Получить источники",
    operation_id="getSources",
)
async def sources(
    db: DB,
    actor: SourcesAdmin,
    q: str = "",
    status: str = "ALL",
    enabled: str = "all",
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> SourcesResponse:
    return await list_sources(db, q=q, status=status, enabled=enabled, page=page, limit=limit)


@router.get(
    "/{source_id}/sync-state",
    response_model=SourceSyncStateOut,
    summary="Получить checkpoint синхронизации источника",
    operation_id="getSourceSyncState",
)
async def source_sync_state(source_id: UUID, db: DB, actor: SourcesAdmin) -> SourceSyncStateOut:
    source = await get_source_record(db, source_id)
    return source_sync_state_to_schema(await get_or_create_sync_state(db, source))


@router.get(
    "/{source_id}",
    response_model=SourceOut,
    summary="Получить источник",
    operation_id="getSource",
)
async def source_detail(source_id: UUID, db: DB, actor: SourcesAdmin) -> SourceOut:
    return source_to_schema(await get_source_record(db, source_id))


@router.patch(
    "/{source_id}",
    response_model=SourceOut,
    summary="Обновить источник",
    operation_id="updateSource",
)
async def source_update(
    source_id: UUID,
    payload: SourceUpdateRequest,
    request: Request,
    db: DB,
    actor: SourcesAdmin,
) -> SourceOut:
    return await update_source(db, request, actor, source_id, payload)


@router.post(
    "/{source_id}/test",
    response_model=SourceConnectionResultOut,
    summary="Проверить источник",
    operation_id="testSourceConnection",
)
async def source_test(
    source_id: UUID, request: Request, db: DB, actor: SourcesAdmin
) -> SourceConnectionResultOut:
    return await test_source_connection(db, request, actor, source_id)


@router.post(
    "/{source_id}/sync",
    response_model=BackgroundJobOut,
    summary="Создать задание синхронизации",
    operation_id="startSourceSync",
)
async def source_sync(
    source_id: UUID,
    request: Request,
    db: DB,
    actor: SourcesAdmin,
    payload: SourceSyncRequest | None = None,
) -> BackgroundJobOut:
    return await start_source_sync(db, request, actor, source_id, payload or SourceSyncRequest())


@router.post(
    "/{source_id}/stop",
    response_model=BackgroundJobOut,
    summary="Остановить синхронизацию",
    operation_id="stopSourceSync",
)
async def source_stop(
    source_id: UUID, request: Request, db: DB, actor: SourcesAdmin
) -> BackgroundJobOut:
    return await stop_source_sync(db, request, actor, source_id)
