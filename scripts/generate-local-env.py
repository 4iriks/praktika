#!/usr/bin/env python3
"""Create a safe local Compose environment without exposing generated secrets."""

from __future__ import annotations

import argparse
import os
import secrets
from pathlib import Path


def build_environment(*, postgres_password: str | None = None) -> str:
    postgres_password = postgres_password or secrets.token_urlsafe(36)
    bootstrap_password = secrets.token_urlsafe(24) + "Aa1"
    return f"""# Generated locally by scripts/generate-local-env.py. Do not commit.
POSTGRES_DB=pyanswer
POSTGRES_USER=pyanswer
POSTGRES_PASSWORD={postgres_password}
POSTGRES_PORT=5432
BACKEND_PORT=8000
FRONTEND_PORT=8080

APP_ENV=development
APP_NAME=PyAnswer API
APP_VERSION=0.7.0
DEBUG=false
FRONTEND_ORIGINS=[\"http://localhost:8080\"]
COOKIE_SECURE=false
COOKIE_SAMESITE=lax
SEED_DEMO_DATA=false
BOOTSTRAP_ADMIN_EMAIL=admin@pyanswer.local
BOOTSTRAP_ADMIN_PASSWORD={bootstrap_password}
BOOTSTRAP_ADMIN_NAME=Администратор

STACK_EXCHANGE_SITE=ru.stackoverflow
STACK_EXCHANGE_TAG=python
STACK_EXCHANGE_TARGET_DOCUMENTS=25000
STACKEXCHANGE_KEY=
WORKER_POLL_INTERVAL_SECONDS=2
WORKER_LEASE_SECONDS=60
WORKER_HEARTBEAT_SECONDS=15
WORKER_MAX_ATTEMPTS=5

QDRANT_URL=http://qdrant:6333
QDRANT_ALIAS=pyanswer_chunks_current
OLLAMA_BASE_URL=http://ollama:11434
EMBEDDING_MODEL=qwen3-embedding:0.6b
EMBEDDING_DIMENSIONS=1024
RERANKER_MODEL=Qwen/Qwen3-Reranker-0.6B
LLM_MODEL=qwen3:8b
LLM_THINK=false

PROJECT_DISK_WARNING_GB=27
PROJECT_DISK_CRITICAL_GB=30
PROJECT_DISK_LIMIT_GB=35
BACKUP_RETENTION_COUNT=3
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate PyAnswer local .env")
    parser.add_argument("--path", type=Path, default=Path(".env"))
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--reuse-postgres-environment",
        action="store_true",
        help="Reuse POSTGRES_PASSWORD from this process environment without printing it",
    )
    args = parser.parse_args()
    target = args.path.resolve()
    if target.exists() and not args.force:
        print(f"Environment already exists: {target}")
        return 0
    existing_password = None
    if args.reuse_postgres_environment:
        existing_password = os.environ.get("POSTGRES_PASSWORD")
        if not existing_password:
            raise RuntimeError("POSTGRES_PASSWORD is missing from the process environment")
    target.write_text(build_environment(postgres_password=existing_password), encoding="utf-8")
    os.chmod(target, 0o600)
    print(f"Environment created: {target}; generated secrets were not printed")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
