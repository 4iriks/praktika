from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path


class ReportStatus(StrEnum):
    PASSED = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    NOT_RUN = "NOT_RUN"


@dataclass(frozen=True, slots=True)
class CheckResult:
    code: str
    status: ReportStatus
    message: str
    actual: object | None = None
    expected: object | None = None
    required: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def overall_status(checks: list[CheckResult]) -> ReportStatus:
    if any(
        item.required and item.status in {ReportStatus.FAIL, ReportStatus.NOT_RUN}
        for item in checks
    ):
        return ReportStatus.FAIL
    if any(item.status in {ReportStatus.WARNING, ReportStatus.NOT_RUN} for item in checks):
        return ReportStatus.WARNING
    return ReportStatus.PASSED


def generated_at() -> str:
    return datetime.now(UTC).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def tree_size(path: Path) -> int | None:
    if not path.exists():
        return None
    if path.is_file():
        return path.stat().st_size
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def git_commit(repo_root: Path) -> str:
    git_dir = repo_root / ".git"
    if not (git_dir / "HEAD").exists():
        return "UNKNOWN"
    head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    if not head.startswith("ref: "):
        return head
    reference = git_dir / head.removeprefix("ref: ")
    if reference.exists():
        return reference.read_text(encoding="utf-8").strip()
    packed = git_dir / "packed-refs"
    if packed.exists():
        ref_name = head.removeprefix("ref: ")
        for line in packed.read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#") and line.endswith(f" {ref_name}"):
                return line.split(" ", 1)[0]
    return "UNKNOWN"


def write_report(
    json_path: Path,
    *,
    title: str,
    payload: dict[str, object],
    checks: list[CheckResult] | None = None,
) -> tuple[Path, Path]:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    document = dict(payload)
    document.setdefault("generatedAt", generated_at())
    if checks is not None:
        document["status"] = overall_status(checks)
        document["checks"] = [item.to_dict() for item in checks]
    json_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    markdown_path = json_path.with_suffix(".md")
    markdown_path.write_text(_markdown(title, document, checks), encoding="utf-8")
    return json_path, markdown_path


def _markdown(
    title: str,
    document: dict[str, object],
    checks: list[CheckResult] | None,
) -> str:
    lines = [f"# {title}", "", f"Generated: `{document['generatedAt']}`", ""]
    if checks is not None:
        lines.extend(
            [
                f"Overall status: **{document['status']}**",
                "",
                "| Check | Status | Actual | Expected | Message |",
                "|---|---|---:|---:|---|",
            ]
        )
        for item in checks:
            actual = "—" if item.actual is None else item.actual
            expected = "—" if item.expected is None else item.expected
            lines.append(
                f"| `{item.code}` | **{item.status}** | {actual} | {expected} | {item.message} |"
            )
    else:
        lines.extend(
            ["```json", json.dumps(document, ensure_ascii=False, indent=2, default=str), "```"]
        )
    return "\n".join(lines) + "\n"
