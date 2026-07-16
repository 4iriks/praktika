from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy import select

from app.db.models.content import Document
from app.db.session import SessionFactory
from app.evaluation.rag import evaluate_rag_records, stable_rag_dataset_hash

DATASET = Path(__file__).parents[2] / "evaluation" / "rag.jsonl"


async def run() -> None:
    parser = argparse.ArgumentParser(description="Evaluate grounded PyAnswer RAG responses")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api")
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--output", type=Path, default=Path("rag-evaluation.json"))
    args = parser.parse_args()
    labels = [json.loads(line) for line in args.dataset.read_text().splitlines() if line.strip()]
    external_ids = {item for label in labels for item in label.get("expectedExternalIds", [])}
    async with SessionFactory() as db:
        pairs = (
            await db.execute(
                select(Document.external_id, Document.id).where(
                    Document.external_id.in_(external_ids)
                )
            )
        ).all()
    document_ids = {external_id: str(document_id) for external_id, document_id in pairs}
    evaluated: list[dict[str, object]] = []
    latencies: list[float] = []
    async with httpx.AsyncClient(base_url=args.base_url, timeout=180) as client:
        csrf_response = await client.get("/auth/csrf")
        csrf_response.raise_for_status()
        csrf = csrf_response.json()["token"]
        for label in labels:
            started = time.perf_counter()
            response = await client.post(
                "/ask",
                headers={"X-CSRF-Token": csrf},
                json={
                    "question": label["query"],
                    "mode": "hybrid",
                    "clientRequestId": f"rag-eval-{label['id']}",
                },
            )
            response.raise_for_status()
            payload = response.json()
            latencies.append((time.perf_counter() - started) * 1000)
            evaluated.append(
                {
                    **label,
                    "expectedSourceIds": [
                        document_ids[item]
                        for item in label.get("expectedExternalIds", [])
                        if item in document_ids
                    ],
                    "returnedSourceIds": [source["documentId"] for source in payload["sources"]],
                    "answer": payload["answer"],
                    "citationValidationPassed": payload["citationValidationPassed"],
                    "insufficientContext": payload["insufficientContext"],
                }
            )
    metrics = evaluate_rag_records(evaluated)
    report = {
        "createdAt": datetime.now(UTC).isoformat(),
        "datasetHash": stable_rag_dataset_hash(labels),
        "records": len(evaluated),
        "metrics": asdict(metrics),
        "latencyP50Ms": _percentile(latencies, 0.5),
        "latencyP95Ms": _percentile(latencies, 0.95),
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(_markdown(report))


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))]


def _markdown(report: dict[str, object]) -> str:
    metrics = report["metrics"]
    assert isinstance(metrics, dict)
    return (
        "# RAG evaluation\n\n"
        f"Dataset: `{report['datasetHash']}`; records: {report['records']}\n\n"
        "| Source recall | Citation validity | Key points | Insufficient accuracy | "
        "p50 ms | p95 ms |\n"
        "|---:|---:|---:|---:|---:|---:|\n"
        f"| {metrics['source_recall']:.3f} | {metrics['citation_validity']:.3f} | "
        f"{metrics['key_point_coverage']:.3f} | "
        f"{metrics['insufficient_context_accuracy']:.3f} | "
        f"{report['latencyP50Ms']:.0f} | {report['latencyP95Ms']:.0f} |\n"
    )


if __name__ == "__main__":
    asyncio.run(run())
