from __future__ import annotations


class StackExchangeClientError(Exception):
    def __init__(self, code: str, safe_message: str, *, retryable: bool) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.retryable = retryable


class StackExchangeCancelled(StackExchangeClientError):
    def __init__(self) -> None:
        super().__init__("CANCELLED", "Операция Stack Exchange отменена", retryable=False)


class StackExchangeQuotaLow(StackExchangeClientError):
    def __init__(self, remaining: int, reserve: int) -> None:
        super().__init__(
            "STACKEXCHANGE_QUOTA_LOW",
            "Остаток квоты Stack Exchange достиг безопасного резерва",
            retryable=True,
        )
        self.remaining = remaining
        self.reserve = reserve


class StackExchangeResponseTooLarge(StackExchangeClientError):
    def __init__(self, maximum_bytes: int) -> None:
        super().__init__(
            "STACKEXCHANGE_RESPONSE_TOO_LARGE",
            "Ответ Stack Exchange превысил допустимый размер",
            retryable=False,
        )
        self.maximum_bytes = maximum_bytes


class StackExchangePermanentError(StackExchangeClientError):
    def __init__(self, code: str = "STACKEXCHANGE_REQUEST_REJECTED") -> None:
        super().__init__(
            code,
            "Stack Exchange отклонил запрос",
            retryable=False,
        )


class StackExchangeRetryExhausted(StackExchangeClientError):
    def __init__(self) -> None:
        super().__init__(
            "STACKEXCHANGE_RETRY_EXHAUSTED",
            "Stack Exchange временно недоступен после ограниченных повторов",
            retryable=True,
        )
