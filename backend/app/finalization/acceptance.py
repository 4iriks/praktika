from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.enums import ProcessingStatus, WorkerInstanceStatus
from app.db.base import utc_now
from app.db.models.content import Document, DocumentChunk
from app.db.models.identity import Role, User
from app.db.models.operations import WorkerInstance
from app.finalization.disk import collect_disk_report
from app.finalization.indexes import index_consistency_checks
from app.finalization.reporting import CheckResult, ReportStatus
from app.integrations.embeddings import OllamaEmbeddingProvider
from app.integrations.llm import OllamaLlmProvider
from app.integrations.qdrant import QdrantIndexClient
from app.integrations.reranker import RerankerClient

LATEST_MIGRATION = "20260716_0006"


async def acceptance_checks(
    db: AsyncSession,
    *,
    settings: Settings,
    repo_root: Path,
    qdrant: QdrantIndexClient,
    embeddings: OllamaEmbeddingProvider,
    llm: OllamaLlmProvider,
    reranker: RerankerClient,
) -> list[CheckResult]:
    checks: list[CheckResult] = []
    await db.execute(text("SELECT 1"))
    checks.append(CheckResult("postgres_ready", ReportStatus.PASSED, "PostgreSQL отвечает"))
    revision = await db.scalar(text("SELECT version_num FROM alembic_version"))
    checks.append(_equal("migrations_at_head", revision, LATEST_MIGRATION))
    real_documents = (
        await db.scalar(
            select(func.count())
            .select_from(Document)
            .where(
                Document.processing_status == ProcessingStatus.CHUNKED,
                ~Document.external_id.like("stage4-%"),
            )
        )
        or 0
    )
    chunks = await db.scalar(select(func.count()).select_from(DocumentChunk)) or 0
    checks.extend(
        [
            CheckResult(
                "real_processed_documents",
                ReportStatus.PASSED
                if real_documents >= settings.acceptance_minimum_documents
                else ReportStatus.FAIL,
                "Минимум считается без Stage 4 demo-документов",
                actual=int(real_documents),
                expected=f">= {settings.acceptance_minimum_documents}",
            ),
            CheckResult(
                "chunks_created",
                ReportStatus.PASSED if chunks > 0 else ReportStatus.FAIL,
                "Обработанный корпус имеет chunks",
                actual=int(chunks),
                expected="> 0",
            ),
        ]
    )
    roles = set((await db.scalars(select(Role.code))).all())
    users = await db.scalar(select(func.count()).select_from(User)) or 0
    checks.append(_equal("roles", roles, {"USER", "EDITOR", "ADMIN"}))
    checks.append(
        CheckResult(
            "users_exist",
            ReportStatus.PASSED if users >= 3 else ReportStatus.FAIL,
            "Пользовательские контуры можно проверить",
            actual=int(users),
            expected=">= 3",
        )
    )
    checks.extend(await _worker_checks(db, settings))
    checks.extend(await index_consistency_checks(db, qdrant, settings))
    embedding_health = await embeddings.health()
    llm_health = await llm.health()
    reranker_health = await reranker.health()
    checks.extend(
        [
            _service(
                "embedding_model",
                embedding_health.online and embedding_health.model_installed,
                embedding_health.message,
            ),
            _service(
                "generation_model",
                llm_health.online and llm_health.model_installed,
                llm_health.message,
            ),
            _service(
                "reranker",
                reranker_health.online and reranker_health.model_ready,
                reranker_health.message,
            ),
        ]
    )
    _, disk_checks = collect_disk_report(
        repo_root,
        warning_gb=settings.project_disk_warning_gb,
        critical_gb=settings.project_disk_critical_gb,
        limit_gb=settings.project_disk_limit_gb,
    )
    checks.extend(disk_checks)
    checks.extend(await _http_checks(settings))
    checks.append(_restore_check(repo_root))
    return checks


async def _http_checks(
    settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
) -> list[CheckResult]:
    checks: list[CheckResult] = []
    timeout = httpx.Timeout(180.0, connect=10.0)
    try:
        async with httpx.AsyncClient(
            base_url=settings.acceptance_api_base_url.rstrip("/") + "/",
            timeout=timeout,
            transport=transport,
        ) as client:
            modes: list[str] = []
            for mode in ("bm25", "vector", "hybrid"):
                response = await client.get(
                    "search",
                    params={
                        "q": "как исправить ModuleNotFoundError при импорте модуля Python",
                        "mode": mode,
                        "page_size": 3,
                        "rerank": "false",
                    },
                )
                if response.status_code == 200 and response.json().get("results"):
                    modes.append(mode)
            checks.append(
                CheckResult(
                    "search_smoke",
                    ReportStatus.PASSED if len(modes) == 3 else ReportStatus.FAIL,
                    "BM25, Vector и Hybrid вызваны через HTTP API",
                    actual=modes,
                    expected=["bm25", "vector", "hybrid"],
                )
            )

            csrf = await _csrf(client)
            rag = await client.post(
                "ask",
                headers={"X-CSRF-Token": csrf},
                json={
                    "question": (
                        "Как исправить ModuleNotFoundError при импорте локального модуля в Python?"
                    ),
                    "mode": "hybrid",
                    "maxSources": 1,
                    "stream": False,
                    "clientRequestId": "stage7-rag-citation-smoke-v2",
                },
            )
            rag_body = rag.json() if rag.status_code == 200 else {}
            rag_ready = bool(
                rag.status_code == 200
                and rag_body.get("responseId")
                and rag_body.get("sources")
                and rag_body.get("citationValidationPassed") is True
            )
            checks.append(
                CheckResult(
                    "rag_smoke",
                    ReportStatus.PASSED if rag_ready else ReportStatus.FAIL,
                    "RAG response должен иметь responseId, sources и валидные citations",
                    actual=rag.status_code,
                    expected=200,
                )
            )
    except (httpx.HTTPError, ValueError) as exc:
        if not any(item.code == "search_smoke" for item in checks):
            checks.append(_http_failure("search_smoke", exc))
        if not any(item.code == "rag_smoke" for item in checks):
            checks.append(_http_failure("rag_smoke", exc))

    password = settings.acceptance_demo_password.get_secret_value()
    if not password:
        checks.append(
            CheckResult(
                "role_login_e2e",
                ReportStatus.NOT_RUN,
                "ACCEPTANCE_DEMO_PASSWORD не задан",
            )
        )
        return checks
    roles: list[str] = []
    try:
        for role, email in (
            ("USER", "user@pyanswer.local"),
            ("EDITOR", "editor@pyanswer.local"),
            ("ADMIN", "admin@pyanswer.local"),
        ):
            async with httpx.AsyncClient(
                base_url=settings.acceptance_api_base_url.rstrip("/") + "/",
                timeout=timeout,
                transport=transport,
            ) as client:
                csrf = await _csrf(client)
                response = await client.post(
                    "auth/login",
                    headers={"X-CSRF-Token": csrf},
                    json={"email": email, "password": password, "remember": False},
                )
                if response.status_code == 200 and response.json().get("role") == role:
                    roles.append(role)
                if response.status_code == 200:
                    logout_csrf = await _csrf(client)
                    await client.post("auth/logout", headers={"X-CSRF-Token": logout_csrf})
    except (httpx.HTTPError, ValueError) as exc:
        checks.append(_http_failure("role_login_e2e", exc))
    else:
        checks.append(
            CheckResult(
                "role_login_e2e",
                ReportStatus.PASSED if len(roles) == 3 else ReportStatus.FAIL,
                "Demo USER, EDITOR и ADMIN прошли HTTP login/logout",
                actual=roles,
                expected=["USER", "EDITOR", "ADMIN"],
            )
        )
    return checks


async def _csrf(client: httpx.AsyncClient) -> str:
    response = await client.get("auth/csrf")
    response.raise_for_status()
    token = response.json().get("csrfToken")
    if not isinstance(token, str) or not token:
        raise ValueError("CSRF token отсутствует")
    return token


def _http_failure(code: str, exc: Exception) -> CheckResult:
    return CheckResult(
        code,
        ReportStatus.FAIL,
        f"HTTP acceptance завершился ошибкой типа {type(exc).__name__}",
    )


def _restore_check(repo_root: Path) -> CheckResult:
    reports = sorted(
        (repo_root / "backups").glob("*/restore-check.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not reports:
        return CheckResult("restore_drill", ReportStatus.NOT_RUN, "Restore report отсутствует")
    try:
        payload = json.loads(reports[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return CheckResult(
            "restore_drill",
            ReportStatus.FAIL,
            f"Restore report нельзя прочитать: {type(exc).__name__}",
        )
    status = payload.get("status")
    return CheckResult(
        "restore_drill",
        ReportStatus.PASSED if status == "PASS" else ReportStatus.FAIL,
        "Проверены checksums, PostgreSQL archive и наличие Qdrant snapshot",
        actual=status,
        expected="PASS",
    )


async def _worker_checks(db: AsyncSession, settings: Settings) -> list[CheckResult]:
    results: list[CheckResult] = []
    now = utc_now()
    for code, capability in (
        ("worker_ingestion_heartbeat", "source_sync"),
        ("worker_indexing_heartbeat", "search_index"),
    ):
        worker = await db.scalar(
            select(WorkerInstance)
            .where(WorkerInstance.capabilities.contains([capability]))
            .order_by(WorkerInstance.heartbeat_at.desc())
            .limit(1)
        )
        online = bool(
            worker
            and worker.status == WorkerInstanceStatus.RUNNING
            and now - worker.heartbeat_at
            <= timedelta(seconds=settings.worker_heartbeat_seconds * 2)
        )
        results.append(_service(code, online, "Проверен heartbeat worker_instances"))
    return results


def _service(code: str, ready: bool, message: str) -> CheckResult:
    return CheckResult(
        code,
        ReportStatus.PASSED if ready else ReportStatus.FAIL,
        message,
        actual="ONLINE" if ready else "OFFLINE/MISSING",
        expected="ONLINE",
    )


def _equal(code: str, actual: object, expected: object) -> CheckResult:
    return CheckResult(
        code,
        ReportStatus.PASSED if actual == expected else ReportStatus.FAIL,
        "Значения совпадают" if actual == expected else "Значения не совпадают",
        actual=actual,
        expected=expected,
    )
