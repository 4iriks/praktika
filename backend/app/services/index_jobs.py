from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.enums import JobStatus, JobType
from app.db.models.content import Document
from app.db.models.operations import Job


async def enqueue_document_reindex(
    db: AsyncSession,
    document: Document,
    *,
    settings: Settings,
    created_by: UUID | None = None,
    force: bool = False,
) -> Job | None:
    """Create one durable reindex job without coupling the transaction to Qdrant."""
    if not force and not settings.auto_enqueue_document_reindex:
        return None
    existing = await db.scalar(
        select(Job).where(
            Job.document_id == document.id,
            Job.type.in_([JobType.DOCUMENT_REINDEX, JobType.DOCUMENT_REPROCESS]),
            Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        )
    )
    if existing is not None:
        return existing
    job = Job(
        type=JobType.DOCUMENT_REINDEX,
        status=JobStatus.QUEUED,
        stage="PREPARING",
        progress=0,
        total_items=1,
        document_id=document.id,
        source_id=document.source_id,
        created_by=created_by,
        cancellable=True,
        payload={"documentId": str(document.id)},
        max_attempts=settings.index_job_max_attempts,
    )
    try:
        async with db.begin_nested():
            db.add(job)
            await db.flush()
    except IntegrityError:
        # The partial unique index is authoritative under concurrent enqueue attempts.
        result = await db.execute(
            select(Job).where(
                Job.document_id == document.id,
                Job.type.in_([JobType.DOCUMENT_REINDEX, JobType.DOCUMENT_REPROCESS]),
                Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            )
        )
        return result.scalar_one_or_none()
    return job
