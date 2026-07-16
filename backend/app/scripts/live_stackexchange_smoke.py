from __future__ import annotations

import asyncio
import os

from app.core.config import get_settings
from app.integrations.stackexchange.client import StackExchangeClient


async def run() -> None:
    if os.environ.get("RUN_LIVE_STACKEXCHANGE_SMOKE") != "1":
        print("LIVE smoke НЕ ВЫПОЛНЕН: задайте RUN_LIVE_STACKEXCHANGE_SMOKE=1")
        return
    settings = get_settings()
    async with StackExchangeClient(settings) as client:
        page = await client.fetch_questions_page(
            page=1,
            page_size=min(settings.stackexchange_page_size, 100),
            sort="activity",
        )
    print(
        "LIVE Stack Exchange smoke: "
        f"items={len(page.envelope.items)}, "
        f"quota={page.envelope.quota_remaining}/{page.envelope.quota_max}, "
        f"has_more={page.envelope.has_more}"
    )


if __name__ == "__main__":
    asyncio.run(run())
