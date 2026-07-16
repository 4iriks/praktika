from __future__ import annotations

import asyncio
import json

from app.db.session import SessionFactory, engine
from app.services.ingestion import ingestion_stats


async def run() -> None:
    async with SessionFactory() as session:
        report = await ingestion_stats(session)
    print(json.dumps(report.model_dump(mode="json", by_alias=True), ensure_ascii=False, indent=2))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
