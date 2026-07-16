from __future__ import annotations

import asyncio
import os
from pathlib import Path

from app.db.session import SessionFactory, engine
from app.finalization.consistency import data_consistency_checks
from app.finalization.reporting import ReportStatus, overall_status, write_report

REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parents[3]))
ARTIFACTS_DIR = Path(os.environ.get("ARTIFACTS_DIR", REPO_ROOT / "artifacts"))


async def run() -> int:
    async with SessionFactory() as db:
        checks = await data_consistency_checks(db)
    write_report(
        ARTIFACTS_DIR / "data-consistency-report.json",
        title="PyAnswer data consistency",
        payload={},
        checks=checks,
    )
    await engine.dispose()
    return 1 if overall_status(checks) == ReportStatus.FAIL else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
