from __future__ import annotations

from collections.abc import Mapping, Sequence

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AuditAction, AuditEntityType, AuditOutcome
from app.db.models.identity import User
from app.db.models.operations import AuditEvent

type JSONScalar = str | int | float | bool | None
type JSONValue = JSONScalar | list[JSONValue] | dict[str, JSONValue]
SENSITIVE_PARTS = (
    "password",
    "hash",
    "salt",
    "digest",
    "session",
    "csrf",
    "cookie",
    "authorization",
    "secret",
    "api_key",
    "apikey",
    "token",
)


def sanitize_audit_value(value: object) -> JSONValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        result: dict[str, JSONValue] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            if any(part in key.casefold() for part in SENSITIVE_PARTS):
                continue
            result[key] = sanitize_audit_value(item)
        return result
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [sanitize_audit_value(item) for item in value]
    return str(value)


async def add_audit_event(
    session: AsyncSession,
    request: Request,
    *,
    actor: User | None,
    action: AuditAction,
    entity_type: AuditEntityType,
    entity_id: str,
    entity_label: str,
    summary: str,
    outcome: AuditOutcome = AuditOutcome.SUCCESS,
    before: Mapping[str, object] | None = None,
    after: Mapping[str, object] | None = None,
    metadata: Mapping[str, object] | None = None,
    batch_id: str | None = None,
    error_code: str | None = None,
) -> AuditEvent:
    client = request.client
    event = AuditEvent(
        actor_user_id=actor.id if actor else None,
        actor_name=actor.name if actor else "Гость",
        actor_role=actor.role.code if actor else None,
        action=action.value,
        entity_type=entity_type.value,
        entity_id=entity_id,
        entity_label=entity_label,
        outcome=outcome.value,
        ip_address=client.host if client else None,
        request_id=getattr(request.state, "request_id", "unknown"),
        batch_id=batch_id,
        summary=summary,
        before=sanitize_audit_value(before) if before else None,
        after=sanitize_audit_value(after) if after else None,
        metadata_json=sanitize_audit_value(metadata) if metadata else None,
        error_code=error_code,
    )
    session.add(event)
    await session.flush()
    return event
