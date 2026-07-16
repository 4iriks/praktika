from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.db.session import SessionFactory, engine
from app.seed.demo import seed_demo_data


async def run() -> None:
    settings = get_settings()
    if not settings.seed_demo_data:
        raise RuntimeError("Установите SEED_DEMO_DATA=true для явного demo seed")
    async with SessionFactory() as session:
        async with session.begin():
            await seed_demo_data(session, settings)
    await engine.dispose()
    logging.getLogger("pyanswer.seed").info("Demo seed завершён")


if __name__ == "__main__":
    asyncio.run(run())
