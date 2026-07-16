from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import DB, require_permission
from app.core.enums import Permission
from app.db.models.identity import User
from app.schemas.management import AdminDashboardOut
from app.services.admin_dashboard import admin_dashboard

router = APIRouter(prefix="/admin", tags=["admin-dashboard"])
AdminViewer = Annotated[User, Depends(require_permission(Permission.ADMIN_ACCESS))]


@router.get(
    "/dashboard",
    response_model=AdminDashboardOut,
    summary="Получить метрики администратора",
    operation_id="getAdminDashboard",
)
async def dashboard(db: DB, actor: AdminViewer) -> AdminDashboardOut:
    return await admin_dashboard(db)
