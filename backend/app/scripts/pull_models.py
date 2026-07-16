from __future__ import annotations

import argparse
import asyncio
import json

import httpx

from app.core.config import get_settings


async def pull(model: str) -> None:
    settings = get_settings()
    timeout = httpx.Timeout(connect=15, read=3600, write=30, pool=15)
    async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=timeout) as client:
        response = await client.post("/api/pull", json={"model": model, "stream": False})
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "success":
            raise RuntimeError("Ollama не подтвердил успешную загрузку модели")
    print(json.dumps({"model": model, "status": "installed"}, ensure_ascii=False))


async def run() -> None:
    parser = argparse.ArgumentParser(description="Явно загрузить локальные модели PyAnswer")
    parser.add_argument("--embedding-only", action="store_true")
    parser.parse_args()
    await pull(get_settings().embedding_model)


if __name__ == "__main__":
    asyncio.run(run())
