from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.db.session import SessionFactory, engine
from app.seed.bootstrap import bootstrap_all


async def run() -> None:
    settings = get_settings()
    async with SessionFactory() as session:
        async with session.begin():
            await bootstrap_all(session, settings)
    await engine.dispose()
    logging.getLogger("pyanswer.bootstrap").info("Bootstrap завершён")


if __name__ == "__main__":
    asyncio.run(run())
