#!/usr/bin/env python3
"""Create a non-secret PyAnswer backup bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit() -> str:
    head = (ROOT / ".git" / "HEAD").read_text(encoding="utf-8").strip()
    if head.startswith("ref: "):
        return (ROOT / ".git" / head[5:]).read_text(encoding="utf-8").strip()
    return head


def create_backup(target: Path, *, postgres_container: str, qdrant_url: str) -> dict[str, object]:
    target.mkdir(parents=True, exist_ok=False)
    dump = target / "postgres.dump"
    temporary = "/tmp/pyanswer-backup.dump"
    subprocess.run(
        [
            "docker",
            "exec",
            postgres_container,
            "pg_dump",
            "-U",
            "pyanswer",
            "-d",
            "pyanswer",
            "--format=custom",
            f"--file={temporary}",
        ],
        check=True,
    )
    try:
        subprocess.run(
            ["docker", "cp", f"{postgres_container}:{temporary}", str(dump)], check=True
        )
    finally:
        subprocess.run(["docker", "exec", postgres_container, "rm", temporary], check=True)
    copied: list[str] = []
    for name in ("corpus-manifest.json", "index-consistency-report.json"):
        source = ROOT / "artifacts" / name
        if source.exists():
            shutil.copy2(source, target / name)
            copied.append(name)
    qdrant = _qdrant_snapshot(target, qdrant_url)
    files = sorted(path for path in target.iterdir() if path.is_file())
    checksums = {path.name: checksum(path) for path in files}
    (target / "checksums.sha256").write_text(
        "".join(f"{digest}  {name}\n" for name, digest in sorted(checksums.items())),
        encoding="utf-8",
    )
    manifest: dict[str, object] = {
        "createdAt": datetime.now(UTC).isoformat(),
        "gitCommit": git_commit(),
        "applicationVersion": "0.7.0",
        "postgres": {"status": "BACKED_UP", "file": dump.name},
        "qdrant": qdrant,
        "copiedManifests": copied,
        "environmentKeys": [
            line.split("=", 1)[0]
            for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#") and "=" in line
        ]
        if (ROOT / ".env").exists()
        else [],
        "checksums": checksums,
        "excluded": [".env", "sessions", "passwords", "API keys", "Ollama models"],
    }
    (target / "backup-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def _qdrant_snapshot(target: Path, base_url: str) -> dict[str, object]:
    try:
        with urllib.request.urlopen(f"{base_url}/aliases", timeout=5) as response:
            aliases = json.load(response)["result"]["aliases"]
        current = next(
            item for item in aliases if item["alias_name"] == "pyanswer_chunks_current"
        )
        collection = current["collection_name"]
        request = urllib.request.Request(
            f"{base_url}/collections/{collection}/snapshots", method="POST", data=b""
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            snapshot_name = json.load(response)["result"]["name"]
        output = target / "qdrant.snapshot"
        with urllib.request.urlopen(
            f"{base_url}/collections/{collection}/snapshots/{snapshot_name}", timeout=60
        ) as response, output.open("wb") as destination:
            shutil.copyfileobj(response, destination)
        return {"status": "BACKED_UP", "collection": collection, "file": output.name}
    except (StopIteration, KeyError, OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"status": "NOT_RUN", "reason": type(exc).__name__}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--postgres-container", default="pyanswer-postgres-1")
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = args.output or ROOT / "backups" / timestamp
    manifest = create_backup(
        target,
        postgres_container=args.postgres_container,
        qdrant_url=args.qdrant_url,
    )
    print(f"Backup created: {target}; Qdrant: {manifest['qdrant']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
