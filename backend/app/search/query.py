from __future__ import annotations

import unicodedata


class QueryValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


def normalize_query(query: str, *, max_characters: int, max_tokens: int) -> str:
    normalized = unicodedata.normalize("NFC", query.replace("\r\n", "\n").replace("\r", "\n"))
    normalized = " ".join(normalized.split())
    if not normalized:
        raise QueryValidationError("SEARCH_QUERY_EMPTY", "Введите поисковый запрос")
    if len(normalized) > max_characters:
        raise QueryValidationError(
            "SEARCH_QUERY_TOO_LONG", f"Запрос ограничен {max_characters} символами"
        )
    # The ingestion tokenizer is deliberately model-independent; this is the same safe estimate.
    estimated_tokens = max(1, (len(normalized) + 3) // 4)
    if estimated_tokens > max_tokens:
        raise QueryValidationError(
            "SEARCH_QUERY_TOO_LONG", f"Запрос ограничен примерно {max_tokens} токенами"
        )
    return normalized
