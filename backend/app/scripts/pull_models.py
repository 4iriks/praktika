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
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--embedding-only", action="store_true")
    group.add_argument("--llm-only", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    if not args.llm_only:
        await pull(settings.embedding_model)
    if not args.embedding_only:
        await pull(settings.llm_model)


if __name__ == "__main__":
    asyncio.run(run())
