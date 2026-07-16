from __future__ import annotations

import asyncio
import os
import time
from uuid import uuid4

import httpx

QUERIES = (
    "Как удалить дубликаты из списка и сохранить порядок?",
    "Чем asyncio.gather отличается от create_task?",
    "Как читать большой CSV в pandas частями?",
    "Как устранить N+1 в Django ORM?",
    "Как задать timeout для requests?",
)


async def run() -> None:
    if os.environ.get("RUN_LIVE_LOCAL_MODELS") != "1":
        print("LIVE local-model smoke НЕ ВЫПОЛНЕН: задайте RUN_LIVE_LOCAL_MODELS=1")
        return
    base_url = os.environ.get("LIVE_API_BASE_URL", "http://127.0.0.1:8000/api")
    async with httpx.AsyncClient(base_url=base_url, timeout=300) as client:
        csrf_response = await client.get("/auth/csrf")
        csrf_response.raise_for_status()
        csrf = csrf_response.json()["token"]
        for query in QUERIES:
            started = time.perf_counter()
            response = await client.post(
                "/ask",
                headers={"X-CSRF-Token": csrf},
                json={
                    "question": query,
                    "mode": "hybrid",
                    "clientRequestId": f"live-local-{uuid4()}",
                },
            )
            response.raise_for_status()
            payload = response.json()
            elapsed = round((time.perf_counter() - started) * 1000)
            print(
                "LIVE",
                payload["model"],
                f"sources={len(payload['sources'])}",
                f"citations={payload['citationValidationPassed']}",
                f"latencyMs={elapsed}",
            )


if __name__ == "__main__":
    asyncio.run(run())
