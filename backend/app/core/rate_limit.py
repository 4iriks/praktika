from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

from app.api.errors import ApiException


@dataclass(slots=True)
class InMemoryRateLimiter:
    limit: int
    window_seconds: int
    enabled: bool = True
    _requests: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))

    def check(self, key: str, now: float | None = None) -> None:
        if not self.enabled:
            return
        current = time.monotonic() if now is None else now
        entries = self._requests[key]
        while entries and current - entries[0] >= self.window_seconds:
            entries.popleft()
        if len(entries) >= self.limit:
            raise ApiException(429, "RATE_LIMITED", "Слишком много попыток. Повторите позже")
        entries.append(current)

    def clear(self) -> None:
        self._requests.clear()
