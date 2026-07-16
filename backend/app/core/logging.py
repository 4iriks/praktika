from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime

SENSITIVE_KEYS = frozenset(
    {
        "password",
        "passwordhash",
        "password_hash",
        "authorization",
        "cookie",
        "session",
        "sessiontoken",
        "csrftoken",
        "secret",
        "apikey",
        "api_key",
    }
)


def sanitize_log_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return {
        key: "[REDACTED]" if key.lower() in SENSITIVE_KEYS else item for key, item in value.items()
    }


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")


def log_request(fields: Mapping[str, object]) -> None:
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": "INFO",
        "message": "http_request",
        **sanitize_log_mapping(fields),
    }
    logging.getLogger("pyanswer.request").info(json.dumps(payload, ensure_ascii=False))


def log_exception(fields: Mapping[str, object], exception: Exception) -> None:
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": "ERROR",
        "message": "unhandled_api_error",
        **sanitize_log_mapping(fields),
    }
    logging.getLogger("pyanswer.error").error(
        json.dumps(payload, ensure_ascii=False),
        exc_info=exception,
    )
