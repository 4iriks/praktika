from __future__ import annotations

import shutil
from pathlib import Path

from app.finalization.reporting import CheckResult, ReportStatus, generated_at, tree_size


def collect_disk_report(
    repo_root: Path,
    *,
    warning_gb: float,
    critical_gb: float,
    limit_gb: float,
) -> tuple[dict[str, object], list[CheckResult]]:
    paths = {
        "applicationSource": repo_root,
        "frontendBuild": repo_root / "frontend" / "dist",
        "logs": repo_root / "logs",
        "backups": repo_root / "backups",
        "rawArchive": repo_root / "data" / "raw",
    }
    components = {name: tree_size(path) for name, path in paths.items()}
    known_total = sum(value for value in components.values() if value is not None)
    usage = shutil.disk_usage(repo_root)
    known_gb = known_total / 1024**3
    status = ReportStatus.PASSED
    if known_gb > critical_gb:
        status = ReportStatus.FAIL
    elif known_gb > warning_gb:
        status = ReportStatus.WARNING
    checks = [
        CheckResult(
            code="known_project_disk_budget",
            status=status,
            message="Сумма доступных приложению путей; Docker volumes измеряются отдельно",
            actual=round(known_gb, 3),
            expected=f"< {critical_gb} GB",
        ),
        CheckResult(
            code="filesystem_free_space",
            status=ReportStatus.PASSED if usage.free / 1024**3 >= 5 else ReportStatus.WARNING,
            message="Свободное место файловой системы",
            actual=round(usage.free / 1024**3, 3),
            expected=">= 5 GB",
            required=False,
        ),
    ]
    return (
        {
            "generatedAt": generated_at(),
            "componentsBytes": components,
            "knownTotalBytes": known_total,
            "filesystemTotalBytes": usage.total,
            "filesystemFreeBytes": usage.free,
            "thresholdsGb": {
                "warning": warning_gb,
                "critical": critical_gb,
                "limit": limit_gb,
            },
            "unavailableWithoutHostCollector": [
                "PostgreSQL Docker volume",
                "Qdrant Docker volume",
                "Ollama model volume",
                "Docker image layers",
            ],
            "fullImportForecastBytes": None,
        },
        checks,
    )
