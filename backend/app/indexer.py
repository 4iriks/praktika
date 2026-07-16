from __future__ import annotations

import asyncio
import signal

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionFactory, engine
from app.workers.indexer import IndexerRunner


async def run_indexer() -> None:
    configure_logging()
    runner = IndexerRunner(session_factory=SessionFactory, settings=get_settings())
    loop = asyncio.get_running_loop()
    for signal_number in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signal_number, runner.request_shutdown)
    try:
        await runner.run()
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(run_indexer())


if __name__ == "__main__":
    main()
