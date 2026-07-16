from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import DB, require_permission
from app.api.pagination import parse_optional_datetime
from app.core.enums import Permission
from app.db.models.identity import User
from app.schemas.management import AuditEventOut, AuditEventsResponse
from app.services.admin_audit import get_audit_event, list_audit_events

router = APIRouter(prefix="/admin/audit", tags=["admin-audit"])
AuditViewer = Annotated[User, Depends(require_permission(Permission.AUDIT_VIEW))]


@router.get(
    "",
    response_model=AuditEventsResponse,
    summary="Получить журнал аудита",
    operation_id="getAuditEvents",
)
async def events(
    db: DB,
    actor_user: AuditViewer,
    q: str = "",
    actor: str = "",
    role: str = "ALL",
    action: str = "ALL",
    entity_type: str = "ALL",
    outcome: str = "ALL",
    date_from: str = "",
    date_to: str = "",
    sort: str = "created_desc",
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> AuditEventsResponse:
    return await list_audit_events(
        db,
        q=q,
        actor=actor,
        role=role,
        action=action,
        entity_type=entity_type,
        outcome=outcome,
        date_from=parse_optional_datetime(date_from),
        date_to=parse_optional_datetime(date_to),
        sort=sort,
        page=page,
        limit=limit,
    )


@router.get(
    "/{event_id}",
    response_model=AuditEventOut,
    summary="Получить событие аудита",
    operation_id="getAuditEvent",
)
async def event_detail(event_id: UUID, db: DB, actor: AuditViewer) -> AuditEventOut:
    return await get_audit_event(db, event_id)
