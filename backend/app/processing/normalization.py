from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMETERS = frozenset(
    {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref"}
)


def canonical_stackoverflow_question_url(question_id: int, supplied_url: str) -> str:
    if question_id <= 0:
        raise ValueError("Stack Overflow question ID должен быть положительным")
    try:
        parsed = urlsplit(supplied_url)
    except ValueError:
        parsed = urlsplit("")
    if parsed.hostname and parsed.hostname.casefold() not in {
        "ru.stackoverflow.com",
        "stackoverflow.com",
    }:
        raise ValueError("Question URL не относится к разрешённому Stack Overflow host")
    return f"https://ru.stackoverflow.com/questions/{question_id}"


def normalize_source_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Source URL должен быть абсолютным HTTP(S) URL")
    host = parsed.hostname.casefold()
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path.rstrip("/") or "/"
    query = urlencode(
        sorted(
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if key.casefold() not in TRACKING_PARAMETERS
        )
    )
    return urlunsplit((parsed.scheme.casefold(), host + port, path, query, ""))
