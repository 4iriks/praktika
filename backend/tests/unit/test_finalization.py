from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.core.config import Settings
from app.finalization.acceptance import _http_checks, _restore_check
from app.finalization.disk import collect_disk_report
from app.finalization.reporting import (
    CheckResult,
    ReportStatus,
    git_commit,
    overall_status,
    sha256_file,
    tree_size,
    write_report,
)


def test_reporting_writes_factual_json_and_markdown(tmp_path: Path) -> None:
    payload_file = tmp_path / "payload.txt"
    payload_file.write_text("pyanswer", encoding="utf-8")
    checks = [
        CheckResult("zero", ReportStatus.PASSED, "ok", actual=0, expected=0),
        CheckResult(
            "optional",
            ReportStatus.NOT_RUN,
            "optional",
            required=False,
        ),
    ]

    json_path, markdown_path = write_report(
        tmp_path / "report.json",
        title="Report",
        payload={"value": 1},
        checks=checks,
    )

    document = json.loads(json_path.read_text(encoding="utf-8"))
    assert document["status"] == "WARNING"
    assert "| `zero` | **PASS** | 0 | 0 |" in markdown_path.read_text(encoding="utf-8")
    assert sha256_file(payload_file) == sha256_file(payload_file)
    assert tree_size(payload_file) == len("pyanswer")
    assert tree_size(tmp_path) is not None
    assert tree_size(tmp_path / "missing") is None


def test_overall_status_respects_required_not_run() -> None:
    assert overall_status([]) == ReportStatus.PASSED
    assert overall_status([CheckResult("x", ReportStatus.FAIL, "x")]) == ReportStatus.FAIL
    assert overall_status([CheckResult("x", ReportStatus.NOT_RUN, "x")]) == ReportStatus.FAIL


def test_git_commit_reads_loose_and_detached_head(tmp_path: Path) -> None:
    git = tmp_path / ".git"
    reference = git / "refs" / "heads" / "main"
    reference.parent.mkdir(parents=True)
    reference.write_text("abc123\n", encoding="utf-8")
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    assert git_commit(tmp_path) == "abc123"
    (git / "HEAD").write_text("def456\n", encoding="utf-8")
    assert git_commit(tmp_path) == "def456"
    assert git_commit(tmp_path / "missing") == "UNKNOWN"


def test_disk_report_uses_real_thresholds(tmp_path: Path) -> None:
    (tmp_path / "frontend" / "dist").mkdir(parents=True)
    (tmp_path / "frontend" / "dist" / "index.html").write_text("ok", encoding="utf-8")
    payload, checks = collect_disk_report(
        tmp_path,
        warning_gb=27,
        critical_gb=30,
        limit_gb=35,
    )
    assert payload["thresholdsGb"] == {"warning": 27, "critical": 30, "limit": 35}
    assert checks[0].status == ReportStatus.PASSED
    assert checks[1].actual is not None


@pytest.mark.asyncio
async def test_acceptance_http_checks_cover_search_rag_and_roles() -> None:
    role_by_email = {
        "user@pyanswer.local": "USER",
        "editor@pyanswer.local": "EDITOR",
        "admin@pyanswer.local": "ADMIN",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/search":
            return httpx.Response(200, json={"results": [{"documentId": "doc"}]})
        if request.url.path == "/api/auth/csrf":
            return httpx.Response(200, json={"csrfToken": "csrf"})
        if request.url.path == "/api/ask":
            return httpx.Response(
                200,
                json={
                    "responseId": "response",
                    "sources": [{"documentId": "doc"}],
                    "citationValidationPassed": True,
                },
            )
        if request.url.path == "/api/auth/login":
            body = json.loads(request.content)
            return httpx.Response(200, json={"role": role_by_email[body["email"]]})
        if request.url.path == "/api/auth/logout":
            return httpx.Response(204)
        return httpx.Response(404)

    settings = Settings(
        APP_ENV="test",
        ACCEPTANCE_API_BASE_URL="http://test/api",
        ACCEPTANCE_DEMO_PASSWORD="Demo123!",
    )
    checks = await _http_checks(settings, transport=httpx.MockTransport(handler))
    assert {check.code: check.status for check in checks} == {
        "search_smoke": ReportStatus.PASSED,
        "rag_smoke": ReportStatus.PASSED,
        "role_login_e2e": ReportStatus.PASSED,
    }


def test_restore_check_reads_latest_report(tmp_path: Path) -> None:
    assert _restore_check(tmp_path).status == ReportStatus.NOT_RUN
    report = tmp_path / "backups" / "20260716" / "restore-check.json"
    report.parent.mkdir(parents=True)
    report.write_text('{"status":"PASS"}', encoding="utf-8")
    assert _restore_check(tmp_path).status == ReportStatus.PASSED
