from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import DB, require_permission
from app.core.enums import Permission
from app.db.models.identity import User
from app.schemas.management import (
    SystemSettingsOut,
    SystemSettingsUpdate,
    SystemStatusOut,
)
from app.services.system import (
    get_settings_record,
    run_health_check,
    settings_to_schema,
    system_status,
    update_system_settings,
)

router = APIRouter(prefix="/admin/system", tags=["admin-system"])
SystemViewer = Annotated[User, Depends(require_permission(Permission.SYSTEM_VIEW))]
SettingsAdmin = Annotated[User, Depends(require_permission(Permission.SYSTEM_SETTINGS_MANAGE))]


@router.get(
    "",
    response_model=SystemStatusOut,
    summary="Получить состояние системы",
    operation_id="getSystemStatus",
)
async def status(db: DB, actor: SystemViewer) -> SystemStatusOut:
    return await system_status(db)


@router.post(
    "/health-check",
    response_model=SystemStatusOut,
    summary="Проверить состояние сервисов",
    operation_id="runSystemHealthCheck",
)
async def health_check(request: Request, db: DB, actor: SystemViewer) -> SystemStatusOut:
    return await run_health_check(db, request, actor)


@router.get(
    "/settings",
    response_model=SystemSettingsOut,
    summary="Получить системные настройки",
    operation_id="getSystemSettings",
)
async def settings(db: DB, actor: SystemViewer) -> SystemSettingsOut:
    return settings_to_schema(await get_settings_record(db))


@router.patch(
    "/settings",
    response_model=SystemSettingsOut,
    summary="Обновить системные настройки",
    operation_id="updateSystemSettings",
)
async def settings_update(
    payload: SystemSettingsUpdate,
    request: Request,
    db: DB,
    actor: SettingsAdmin,
) -> SystemSettingsOut:
    return await update_system_settings(db, request, actor, payload)
