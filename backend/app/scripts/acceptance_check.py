from __future__ import annotations

import asyncio
import os
from pathlib import Path

from app.core.config import get_settings
from app.db.session import SessionFactory, engine
from app.finalization.acceptance import acceptance_checks
from app.finalization.reporting import ReportStatus, overall_status, write_report
from app.integrations.embeddings import OllamaEmbeddingProvider
from app.integrations.llm import OllamaLlmProvider
from app.integrations.qdrant import QdrantIndexClient
from app.integrations.reranker import RerankerClient

REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parents[3]))
ARTIFACTS_DIR = Path(os.environ.get("ARTIFACTS_DIR", REPO_ROOT / "artifacts"))


async def run() -> int:
    settings = get_settings()
    qdrant = QdrantIndexClient(settings)
    embeddings = OllamaEmbeddingProvider(settings)
    llm = OllamaLlmProvider(settings)
    reranker = RerankerClient(settings)
    try:
        async with SessionFactory() as db:
            checks = await acceptance_checks(
                db,
                settings=settings,
                repo_root=REPO_ROOT,
                qdrant=qdrant,
                embeddings=embeddings,
                llm=llm,
                reranker=reranker,
            )
    finally:
        await qdrant.close()
        await embeddings.close()
        await llm.close()
        await reranker.close()
    write_report(
        ARTIFACTS_DIR / "acceptance-report.json",
        title="PyAnswer final acceptance",
        payload={},
        checks=checks,
    )
    await engine.dispose()
    return 1 if overall_status(checks) == ReportStatus.FAIL else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
