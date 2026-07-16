from __future__ import annotations

import asyncio
import os
from pathlib import Path

from app.db.session import SessionFactory, engine
from app.finalization.corpus import collect_corpus_manifest
from app.finalization.reporting import write_report

REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parents[3]))
ARTIFACTS_DIR = Path(os.environ.get("ARTIFACTS_DIR", REPO_ROOT / "artifacts"))


async def run() -> None:
    async with SessionFactory() as db:
        payload = await collect_corpus_manifest(db, repo_root=REPO_ROOT)
    paths = write_report(
        ARTIFACTS_DIR / "corpus-manifest.json",
        title="PyAnswer corpus manifest",
        payload=payload,
    )
    print("\n".join(str(path) for path in paths))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
