from __future__ import annotations

from uuid import uuid4

from app.db.repositories.jobs import (
    StaleRecoveryResult,
    sanitize_job_event_message,
    sanitize_job_event_metrics,
)


def test_job_event_sanitizer_removes_nested_credentials_and_url_secrets() -> None:
    secret = "stackexchange-private-key"
    sanitized = sanitize_job_event_metrics(
        {
            "requestUrl": f"https://api.stackexchange.com/2.3/questions?key={secret}&site=ru",
            "stackexchangeKey": secret,
            "contentHash": "safe-content-hash",
            "nested": {
                "sessionToken": "raw-session",
                "csrf": "raw-csrf",
                "quota": 100,
            },
        }
    )

    serialized = str(sanitized)
    assert secret not in serialized
    assert "raw-session" not in serialized
    assert "raw-csrf" not in serialized
    assert sanitized["contentHash"] == "safe-content-hash"
    assert sanitized["nested"] == {"quota": 100}


def test_job_event_message_redacts_headers_and_control_characters() -> None:
    message = (
        "retry\x00 Authorization=Bearer-secret Cookie=session-value "
        "Bearer abc.def.ghi api_key=private"
    )

    sanitized = sanitize_job_event_message(message)

    assert "\x00" not in sanitized
    assert "Bearer-secret" not in sanitized
    assert "session-value" not in sanitized
    assert "abc.def.ghi" not in sanitized
    assert "private" not in sanitized
    assert sanitized.count("[REDACTED]") >= 3


def test_stale_recovery_result_counts_all_terminal_outcomes() -> None:
    result = StaleRecoveryResult(
        requeued_job_ids=(uuid4(), uuid4()),
        failed_job_ids=(uuid4(),),
        cancelled_job_ids=(uuid4(),),
    )

    assert result.recovered_count == 4
