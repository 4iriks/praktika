from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiException
from app.db.models.operations import AuditEvent
from app.schemas.base import pagination
from app.schemas.management import AuditEventOut, AuditEventsResponse
from app.services.management_serializers import audit_to_schema


async def get_audit_event(db: AsyncSession, event_id: UUID) -> AuditEventOut:
    event = await db.get(AuditEvent, event_id)
    if event is None:
        raise ApiException(404, "NOT_FOUND", "Событие аудита не найдено")
    return audit_to_schema(event)


async def list_audit_events(
    db: AsyncSession,
    *,
    q: str,
    actor: str,
    role: str,
    action: str,
    entity_type: str,
    outcome: str,
    date_from: datetime | None,
    date_to: datetime | None,
    sort: str,
    page: int,
    limit: int,
) -> AuditEventsResponse:
    filters = []
    if q:
        filters.append(
            or_(
                AuditEvent.summary.ilike(f"%{q}%"),
                AuditEvent.request_id.ilike(f"%{q}%"),
                AuditEvent.entity_label.ilike(f"%{q}%"),
            )
        )
    if actor:
        try:
            actor_id = UUID(actor)
        except ValueError:
            filters.append(AuditEvent.actor_name.ilike(f"%{actor}%"))
        else:
            filters.append(
                or_(
                    AuditEvent.actor_name.ilike(f"%{actor}%"),
                    AuditEvent.actor_user_id == actor_id,
                )
            )
    if role != "ALL":
        filters.append(AuditEvent.actor_role == role)
    if action != "ALL":
        filters.append(AuditEvent.action == action)
    if entity_type != "ALL":
        filters.append(AuditEvent.entity_type == entity_type)
    if outcome != "ALL":
        filters.append(AuditEvent.outcome == outcome)
    if date_from:
        filters.append(AuditEvent.created_at >= date_from)
    if date_to:
        filters.append(AuditEvent.created_at <= date_to)
    total = await db.scalar(select(func.count()).select_from(AuditEvent).where(*filters)) or 0
    statement = select(AuditEvent).where(*filters)
    if sort == "created_desc":
        statement = statement.order_by(AuditEvent.created_at.desc(), AuditEvent.id)
    elif sort == "created_asc":
        statement = statement.order_by(AuditEvent.created_at.asc(), AuditEvent.id)
    else:
        raise ApiException(422, "VALIDATION_ERROR", "Неизвестная сортировка")
    items = (await db.scalars(statement.offset((page - 1) * limit).limit(limit))).all()
    return AuditEventsResponse(
        items=[audit_to_schema(item) for item in items],
        pagination=pagination(page, limit, total),
    )
