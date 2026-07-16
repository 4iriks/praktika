from __future__ import annotations

import os
from pathlib import Path

from app.core.config import get_settings
from app.finalization.disk import collect_disk_report
from app.finalization.reporting import write_report


def run() -> None:
    settings = get_settings()
    repo_root = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parents[3]))
    payload, checks = collect_disk_report(
        repo_root,
        warning_gb=settings.project_disk_warning_gb,
        critical_gb=settings.project_disk_critical_gb,
        limit_gb=settings.project_disk_limit_gb,
    )
    artifacts_dir = Path(os.environ.get("ARTIFACTS_DIR", repo_root / "artifacts"))
    write_report(
        artifacts_dir / "disk-report.json",
        title="PyAnswer disk report",
        payload=payload,
        checks=checks,
    )


if __name__ == "__main__":
    run()
