from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from app.integrations.stackexchange.errors import StackExchangeCancelled

CancellationCheck = Callable[[], Awaitable[bool]]
AsyncSleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]


async def cancellable_sleep(
    delay: float,
    *,
    cancellation_check: CancellationCheck | None,
    sleep: AsyncSleep = asyncio.sleep,
    quantum: float = 0.25,
) -> None:
    remaining = max(0.0, delay)
    while remaining > 0:
        if cancellation_check is not None and await cancellation_check():
            raise StackExchangeCancelled
        step = min(remaining, quantum)
        await sleep(step)
        remaining -= step
    if cancellation_check is not None and await cancellation_check():
        raise StackExchangeCancelled


class AsyncRateLimiter:
    def __init__(
        self,
        requests_per_second: float,
        *,
        clock: Clock | None = None,
        sleep: AsyncSleep = asyncio.sleep,
    ) -> None:
        self._interval = 1.0 / requests_per_second
        self._clock = clock or asyncio.get_running_loop().time
        self._sleep = sleep
        self._next_request_at = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self, cancellation_check: CancellationCheck | None = None) -> None:
        async with self._lock:
            now = self._clock()
            delay = max(0.0, self._next_request_at - now)
            await cancellable_sleep(
                delay,
                cancellation_check=cancellation_check,
                sleep=self._sleep,
            )
            self._next_request_at = max(self._clock(), self._next_request_at) + self._interval
