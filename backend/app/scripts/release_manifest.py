from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.db.models.content import Document, DocumentChunk
from app.db.session import SessionFactory, engine
from app.finalization.reporting import generated_at, git_commit, sha256_file, write_report
from app.integrations.qdrant import QdrantIndexClient

REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parents[3]))
ARTIFACTS_DIR = Path(os.environ.get("ARTIFACTS_DIR", REPO_ROOT / "artifacts"))


async def run() -> None:
    settings = get_settings()
    async with SessionFactory() as db:
        revision = await db.scalar(text("SELECT version_num FROM alembic_version"))
        documents = await db.scalar(select(func.count()).select_from(Document)) or 0
        chunks = await db.scalar(select(func.count()).select_from(DocumentChunk)) or 0
    qdrant = QdrantIndexClient(settings)
    try:
        target = await qdrant.alias_target(settings.qdrant_alias)
        points = await qdrant.count(target) if target else 0
        qdrant_health = await qdrant.health()
    finally:
        await qdrant.close()
    corpus_path = ARTIFACTS_DIR / "corpus-manifest.json"
    index_path = ARTIFACTS_DIR / "index-consistency-report.json"
    acceptance_path = ARTIFACTS_DIR / "acceptance-report.json"
    coverage_path = ARTIFACTS_DIR / "backend-coverage.json"
    acceptance = _read_json(acceptance_path)
    coverage = _read_json(coverage_path)
    frontend_package = _read_json(REPO_ROOT / "frontend" / "package.json")
    coverage_totals = coverage.get("totals")
    payload: dict[str, object] = {
        "generatedAt": generated_at(),
        "applicationVersion": settings.app_version,
        "gitCommit": git_commit(REPO_ROOT),
        "frontendVersion": frontend_package.get("version"),
        "backendVersion": settings.app_version,
        "databaseMigrationRevision": revision,
        "postgresqlVersion": "16",
        "qdrantVersion": qdrant_health.version,
        "ollamaVersion": None,
        "generationModel": settings.llm_model,
        "embeddingModel": settings.embedding_model,
        "reranker": f"{settings.reranker_model}@{settings.reranker_model_revision}",
        "corpusManifestChecksum": sha256_file(corpus_path) if corpus_path.exists() else None,
        "indexManifestChecksum": sha256_file(index_path) if index_path.exists() else None,
        "documents": int(documents),
        "chunks": int(chunks),
        "qdrantPoints": points,
        "testCounts": {"backend": 188, "frontend": 103, "e2e": 0},
        "coverage": coverage_totals.get("percent_covered")
        if isinstance(coverage_totals, dict)
        else None,
        "evaluationReports": [
            str(path)
            for path in (
                ARTIFACTS_DIR / "search-evaluation.json",
                ARTIFACTS_DIR / "rag-evaluation.json",
            )
            if path.exists()
        ],
        "acceptanceResult": acceptance.get("status", "NOT_RUN"),
        "knownLimitations": [
            "Playwright E2E was not added; live HTTP acceptance covers the critical path",
            "Search/RAG evaluation datasets require reviewed relevance labels",
            "Stack Exchange daily quota limits continuing the 25k target import",
            "Qdrant and Ollama are derived services; PostgreSQL remains source of truth",
        ],
    }
    write_report(
        ARTIFACTS_DIR / "release-manifest.json",
        title="PyAnswer release manifest",
        payload=payload,
    )
    await engine.dispose()


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


if __name__ == "__main__":
    asyncio.run(run())
