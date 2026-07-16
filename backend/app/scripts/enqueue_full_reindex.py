from __future__ import annotations

import asyncio
import os
from typing import Any, cast

from sqlalchemy import update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.enums import JobEventLevel, JobStage, JobStatus, JobType
from app.db.base import utc_now
from app.db.models.operations import Job, JobEvent
from app.db.session import SessionFactory, engine


async def run() -> None:
    if os.environ.get("CONFIRM_INDEX_FULL") != "YES":
        raise SystemExit("Полная индексация не запущена: задайте CONFIRM_INDEX_FULL=YES")

    settings = get_settings()
    async with SessionFactory() as session:
        try:
            async with session.begin():
                now = utc_now()
                superseded = cast(
                    CursorResult[Any],
                    await session.execute(
                        update(Job)
                        .where(
                            Job.type == JobType.DOCUMENT_REINDEX,
                            Job.status == JobStatus.QUEUED,
                        )
                        .values(
                            status=JobStatus.CANCELLED,
                            finished_at=now,
                            updated_at=now,
                            result={"supersededBy": "FULL_REINDEX"},
                        )
                    ),
                )
                job = Job(
                    type=JobType.FULL_REINDEX,
                    status=JobStatus.QUEUED,
                    stage=JobStage.PREPARING,
                    cancellable=True,
                    payload={},
                    max_attempts=settings.index_job_max_attempts,
                )
                session.add(job)
                await session.flush()
                session.add(
                    JobEvent(
                        job_id=job.id,
                        level=JobEventLevel.INFO,
                        stage=JobStage.PREPARING,
                        code="CLI_FULL_REINDEX_ENQUEUED",
                        message=(
                            "Blue-green переиндексация создана доверенной локальной CLI-командой."
                        ),
                        metrics={"supersededDocumentJobs": superseded.rowcount},
                    )
                )
            print(job.id)
        except IntegrityError as exc:
            raise SystemExit("Активная полная переиндексация уже существует") from exc
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
