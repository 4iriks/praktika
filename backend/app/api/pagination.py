from __future__ import annotations

from datetime import UTC, datetime

from app.api.errors import ApiException


def parse_optional_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ApiException(422, "VALIDATION_ERROR", "Некорректная дата фильтра") from exc
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
