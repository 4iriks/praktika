from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models.content import Document
from app.db.session import SessionFactory
from app.evaluation.retrieval import evaluate_rankings, percentile, stable_dataset_hash

DATASET = Path(__file__).parents[2] / "evaluation" / "retrieval.jsonl"


async def run() -> None:
    parser = argparse.ArgumentParser(description="Evaluate PyAnswer retrieval modes")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api")
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--output", type=Path, default=Path("retrieval-evaluation.json"))
    parser.add_argument("--split", choices=["development", "validation"], default="validation")
    args = parser.parse_args()
    records = [json.loads(line) for line in args.dataset.read_text().splitlines() if line.strip()]
    records = [record for record in records if record["split"] == args.split]
    external_ids = {value for record in records for value in record["relevantExternalIds"]}
    async with SessionFactory() as db:
        pairs = (
            await db.execute(
                select(Document.external_id, Document.id).where(
                    Document.external_id.in_(external_ids)
                )
            )
        ).all()
    expected_ids = {external_id: str(document_id) for external_id, document_id in pairs}
    modes = {
        "bm25": ("bm25", False),
        "vector": ("vector", False),
        "hybrid": ("hybrid", False),
        "hybrid_reranker": ("hybrid", True),
    }
    report: dict[str, object] = {}
    async with httpx.AsyncClient(base_url=args.base_url, timeout=60) as client:
        for label, (mode, rerank) in modes.items():
            rankings: list[list[str]] = []
            relevant: list[set[str]] = []
            latencies: list[float] = []
            for record in records:
                response = await client.get(
                    "/search",
                    params={"q": record["query"], "mode": mode, "rerank": rerank, "page_size": 10},
                )
                response.raise_for_status()
                payload = response.json()
                rankings.append([item["documentId"] for item in payload["results"]])
                relevant.append(
                    {
                        expected_ids[external_id]
                        for external_id in record["relevantExternalIds"]
                        if external_id in expected_ids
                    }
                )
                latencies.append(float(payload["metrics"]["tookMs"]))
            metrics = evaluate_rankings(rankings, relevant)
            report[label] = {
                **asdict(metrics),
                "latencyP50Ms": percentile(latencies, 0.5),
                "latencyP95Ms": percentile(latencies, 0.95),
            }
    config = get_settings()
    envelope = {
        "createdAt": datetime.now(UTC).isoformat(),
        "split": args.split,
        "datasetHash": stable_dataset_hash(records),
        "embeddingModel": config.embedding_model,
        "sparseModel": config.sparse_model,
        "rerankerModel": config.reranker_model,
        "rerankerRevision": config.reranker_model_revision,
        "results": report,
    }
    args.output.write_text(json.dumps(envelope, ensure_ascii=False, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(_markdown(envelope))


def _markdown(report: dict[str, object]) -> str:
    lines = ["# Retrieval evaluation", "", f"Dataset: `{report['datasetHash']}`", ""]
    lines.append("| Mode | Recall@5 | Recall@10 | MRR@10 | nDCG@10 | HitRate@5 | p50 ms | p95 ms |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    results = report["results"]
    if isinstance(results, dict):
        for mode, raw in results.items():
            if not isinstance(raw, dict):
                continue
            lines.append(
                f"| {mode} | {raw['recall_at_5']:.3f} | {raw['recall_at_10']:.3f} | "
                f"{raw['mrr_at_10']:.3f} | {raw['ndcg_at_10']:.3f} | "
                f"{raw['hit_rate_at_5']:.3f} | {raw['latencyP50Ms']:.0f} | "
                f"{raw['latencyP95Ms']:.0f} |"
            )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    asyncio.run(run())
