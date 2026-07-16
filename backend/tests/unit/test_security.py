from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.api.errors import ApiException
from app.api.pagination import parse_optional_datetime
from app.core.config import Settings
from app.core.enums import Permission, UserRole
from app.core.permissions import PERMISSION_MATRIX
from app.core.security import (
    PasswordPolicyError,
    PasswordService,
    constant_time_equal,
    generate_opaque_token,
    hash_token,
    validate_password,
)
from app.services.audit import sanitize_audit_value


def test_argon2id_hash_verify_and_reject_raw_password() -> None:
    service = PasswordService.from_settings(
        Settings(
            APP_ENV="test",
            DATABASE_URL="postgresql+asyncpg://x:x@localhost/pyanswer_test",
            ARGON2_TIME_COST=1,
            ARGON2_MEMORY_COST=8192,
            ARGON2_PARALLELISM=1,
        )
    )
    password_hash = service.hash("Strong123")

    assert password_hash.startswith("$argon2id$")
    assert password_hash != "Strong123"
    assert service.verify(password_hash, "Strong123")
    assert not service.verify(password_hash, "Wrong123")


@pytest.mark.parametrize("password", ["short", "lowercase1", "UPPERCASE1", "NoDigitsHere"])
def test_password_policy_is_enforced(password: str) -> None:
    with pytest.raises(PasswordPolicyError):
        validate_password(password)


def test_opaque_tokens_are_random_hashed_and_compared_safely() -> None:
    first = generate_opaque_token()
    second = generate_opaque_token()

    assert first != second
    assert hash_token(first) != first
    assert len(hash_token(first)) == 64
    assert constant_time_equal(first, first)
    assert not constant_time_equal(first, second)


def test_server_permission_matrix_inheritance() -> None:
    user = PERMISSION_MATRIX[UserRole.USER]
    editor = PERMISSION_MATRIX[UserRole.EDITOR]
    admin = PERMISSION_MATRIX[UserRole.ADMIN]

    assert Permission.SEARCH_USE in user
    assert Permission.EDITOR_ACCESS not in user
    assert user < editor < admin
    assert Permission.SYSTEM_SETTINGS_MANAGE in admin


def test_audit_sanitizer_removes_credentials_recursively() -> None:
    sanitized = sanitize_audit_value(
        {
            "email": "user@example.test",
            "password": "secret",
            "nested": {
                "sessionToken": "raw",
                "safe": [1, {"csrf_token": "raw", "value": True}],
            },
        }
    )

    assert sanitized == {
        "email": "user@example.test",
        "nested": {"safe": [1, {"value": True}]},
    }


def test_datetime_parser_is_strict_and_timezone_aware() -> None:
    parsed = parse_optional_datetime("2026-07-15T10:00:00Z")
    assert parsed == datetime(2026, 7, 15, 10, tzinfo=UTC)
    assert parse_optional_datetime("") is None
    with pytest.raises(ApiException) as exc_info:
        parse_optional_datetime("not-a-date")
    assert exc_info.value.code == "VALIDATION_ERROR"


def test_production_configuration_rejects_insecure_defaults() -> None:
    with pytest.raises(ValueError):
        Settings(APP_ENV="production", COOKIE_SECURE=False, SEED_DEMO_DATA=False)
    with pytest.raises(ValueError):
        Settings(FRONTEND_ORIGINS=["*"])
