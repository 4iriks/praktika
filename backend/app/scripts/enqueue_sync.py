from __future__ import annotations

import argparse
import asyncio
import os
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.enums import JobEventLevel, JobStage, JobStatus, JobType, SourceStatus, SourceSyncMode
from app.db.base import utc_now
from app.db.models.operations import Job, JobEvent, Source
from app.db.session import SessionFactory, engine


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Поставить безопасную SOURCE_SYNC job в очередь")
    parser.add_argument("source_id", type=UUID)
    parser.add_argument("--mode", choices=[item.value for item in SourceSyncMode], default="AUTO")
    parser.add_argument("--max-documents", type=int)
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> None:
    if args.max_documents is not None and not 1 <= args.max_documents <= 25_000:
        raise SystemExit("--max-documents должен быть от 1 до 25000")
    if args.max_pages is not None and not 1 <= args.max_pages <= 250:
        raise SystemExit("--max-pages должен быть от 1 до 250")
    uncapped = args.max_documents is None and args.max_pages is None and not args.dry_run
    if uncapped and os.environ.get("CONFIRM_FULL_SYNC") != "YES":
        raise SystemExit("Полный импорт не запущен: задайте лимит или CONFIRM_FULL_SYNC=YES")
    settings = get_settings()
    async with SessionFactory() as session:
        try:
            async with session.begin():
                source = await session.scalar(
                    select(Source).where(Source.id == args.source_id).with_for_update()
                )
                if source is None:
                    raise SystemExit("Источник не найден")
                if not source.enabled:
                    raise SystemExit("Источник отключён")
                payload: dict[str, object] = {
                    "sourceId": str(source.id),
                    "mode": args.mode,
                    "dryRun": args.dry_run,
                }
                if args.max_documents is not None:
                    payload["maxDocuments"] = args.max_documents
                if args.max_pages is not None:
                    payload["maxPages"] = args.max_pages
                job = Job(
                    type=JobType.SOURCE_SYNC,
                    status=JobStatus.QUEUED,
                    stage=JobStage.PREPARING,
                    source_id=source.id,
                    total_items=args.max_documents or source.target_documents,
                    max_attempts=settings.worker_max_attempts,
                    payload=payload,
                    planned_duration_ms=0,
                )
                session.add(job)
                await session.flush()
                session.add(
                    JobEvent(
                        job_id=job.id,
                        level=JobEventLevel.INFO,
                        stage=JobStage.PREPARING,
                        code="CLI_SYNC_ENQUEUED",
                        message="Задание создано доверенной локальной CLI-командой.",
                        metrics={"mode": args.mode, "dryRun": args.dry_run},
                    )
                )
                source.status = SourceStatus.SYNCING
                source.current_job_id = job.id
                source.last_sync_at = utc_now()
            print(job.id)
        except IntegrityError as exc:
            raise SystemExit("Активная синхронизация этого источника уже существует") from exc
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run(arguments()))
