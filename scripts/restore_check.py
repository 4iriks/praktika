#!/usr/bin/env python3
"""Validate a backup without touching the main PostgreSQL or Qdrant volumes."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def checksum(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def validate(path: Path) -> dict[str, object]:
    manifest_path = path / "backup-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    for name, expected in manifest.get("checksums", {}).items():
        candidate = path / name
        if not candidate.exists() or checksum(candidate) != expected:
            errors.append(f"checksum:{name}")
    dump = path / "postgres.dump"
    completed = subprocess.run(
        ["docker", "run", "--rm", "-v", f"{dump.resolve()}:/backup.dump:ro", "postgres:16-alpine", "pg_restore", "--list", "/backup.dump"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        errors.append("postgres_dump_invalid")
    qdrant_status = manifest.get("qdrant", {}).get("status")
    return {
        "status": "PASS" if not errors and qdrant_status == "BACKED_UP" else "WARNING" if not errors else "FAIL",
        "errors": errors,
        "postgresArchive": "PASS" if completed.returncode == 0 else "FAIL",
        "qdrantSnapshot": qdrant_status,
        "destructiveRestorePerformed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("backup", type=Path)
    args = parser.parse_args()
    report = validate(args.backup.resolve())
    output = args.backup / "restore-check.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 1 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
