from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from app.integrations.llm.base import LlmProviderError


@dataclass(frozen=True, slots=True)
class GateSnapshot:
    active: int
    waiting: int
    capacity: int
    queue_limit: int


class InferenceGate:
    def __init__(self, capacity: int, queue_limit: int, timeout_seconds: float) -> None:
        self._semaphore = asyncio.Semaphore(capacity)
        self._capacity = capacity
        self._queue_limit = queue_limit
        self._timeout = timeout_seconds
        self._waiting = 0
        self._active = 0
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        async with self._lock:
            if self._semaphore.locked() and self._waiting >= self._queue_limit:
                raise LlmProviderError("LLM_QUEUE_FULL", "Очередь локальной модели заполнена")
            self._waiting += 1
        try:
            try:
                await asyncio.wait_for(self._semaphore.acquire(), timeout=self._timeout)
            except TimeoutError as exc:
                raise LlmProviderError(
                    "LLM_QUEUE_TIMEOUT", "Истекло время ожидания локальной модели"
                ) from exc
        finally:
            async with self._lock:
                self._waiting -= 1
        async with self._lock:
            self._active += 1
        try:
            yield
        finally:
            async with self._lock:
                self._active -= 1
            self._semaphore.release()

    def snapshot(self) -> GateSnapshot:
        return GateSnapshot(
            active=self._active,
            waiting=self._waiting,
            capacity=self._capacity,
            queue_limit=self._queue_limit,
        )
