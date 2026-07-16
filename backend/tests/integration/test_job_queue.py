from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import JobStage, JobStatus, JobType, WorkerInstanceStatus
from app.db.models.operations import Job, JobEvent, WorkerInstance
from app.db.repositories.jobs import (
    claim_next_job,
    heartbeat_job,
    heartbeat_worker_instance,
    recover_stale_jobs,
    register_worker_instance,
    request_job_cancellation,
    stop_worker_instance,
    update_job_progress,
)
from app.db.session import SessionFactory

pytestmark = pytest.mark.integration
NOW = datetime(2026, 7, 16, 12, tzinfo=UTC)


async def add_worker(
    db: AsyncSession,
    instance_id: str,
    *,
    now: datetime = NOW,
) -> UUID:
    worker = await register_worker_instance(
        db,
        name="PyAnswer ingestion worker",
        instance_id=instance_id,
        capabilities={"source_sync"},
        version="0.5.0",
        hostname="test-worker",
        pid=100,
        now=now,
    )
    return worker.id


async def add_job(
    db: AsyncSession,
    *,
    status: JobStatus = JobStatus.QUEUED,
    next_attempt_at: datetime | None = None,
    claimed_by: UUID | None = None,
    lease_expires_at: datetime | None = None,
    attempt: int = 0,
    max_attempts: int = 5,
    cancellation_requested_at: datetime | None = None,
) -> UUID:
    job = Job(
        type=JobType.HEALTH_CHECK,
        status=status,
        stage=JobStage.PREPARING,
        progress=0,
        next_attempt_at=next_attempt_at,
        claimed_by=claimed_by,
        claimed_at=NOW if claimed_by else None,
        lease_expires_at=lease_expires_at,
        heartbeat_at=NOW if claimed_by else None,
        attempt=attempt,
        max_attempts=max_attempts,
        cancellation_requested_at=cancellation_requested_at,
        cancellable=True,
        payload={},
    )
    db.add(job)
    await db.flush()
    return job.id


async def load_job(job_id: UUID) -> Job:
    async with SessionFactory() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        return job


async def test_atomic_claim_uses_skip_locked_for_two_workers(db: AsyncSession) -> None:
    async with db.begin():
        first_worker = await add_worker(db, "queue-worker-1")
        second_worker = await add_worker(db, "queue-worker-2")
        job_id = await add_job(db)

    async with SessionFactory() as first_session, SessionFactory() as second_session:
        async with first_session.begin():
            claimed = await claim_next_job(
                first_session,
                worker_id=first_worker,
                supported_types={JobType.HEALTH_CHECK},
                lease_seconds=60,
                now=NOW,
            )
            assert claimed is not None and claimed.id == job_id

            async with second_session.begin():
                skipped = await claim_next_job(
                    second_session,
                    worker_id=second_worker,
                    supported_types={JobType.HEALTH_CHECK},
                    lease_seconds=60,
                    now=NOW,
                )
                assert skipped is None

    stored = await load_job(job_id)
    assert stored.status == JobStatus.RUNNING
    assert stored.claimed_by == first_worker
    assert stored.attempt == 1
    assert stored.started_at == NOW
    assert stored.lease_expires_at == NOW + timedelta(seconds=60)


async def test_future_job_is_not_claimed(db: AsyncSession) -> None:
    async with db.begin():
        worker_id = await add_worker(db, "future-worker")
        job_id = await add_job(db, next_attempt_at=NOW + timedelta(minutes=10))

    async with db.begin():
        claimed = await claim_next_job(
            db,
            worker_id=worker_id,
            supported_types={JobType.HEALTH_CHECK},
            lease_seconds=60,
            now=NOW,
        )
    assert claimed is None
    assert (await load_job(job_id)).status == JobStatus.QUEUED


async def test_heartbeat_extends_lease_and_progress_never_moves_backwards(
    db: AsyncSession,
) -> None:
    async with db.begin():
        worker_id = await add_worker(db, "heartbeat-worker")
        job_id = await add_job(db)
    async with db.begin():
        claimed = await claim_next_job(
            db,
            worker_id=worker_id,
            supported_types={JobType.HEALTH_CHECK},
            lease_seconds=60,
            now=NOW,
        )
        assert claimed is not None
    async with db.begin():
        heartbeat = await heartbeat_job(
            db,
            job_id=job_id,
            worker_id=worker_id,
            lease_seconds=60,
            now=NOW + timedelta(seconds=20),
        )
        assert heartbeat is not None
        await update_job_progress(
            db,
            job_id=job_id,
            worker_id=worker_id,
            progress=70,
            processed_items=70,
            total_items=100,
            stage=JobStage.PROCESSING,
            request_count_delta=2,
            bytes_received_delta=1024,
        )
        await update_job_progress(
            db,
            job_id=job_id,
            worker_id=worker_id,
            progress=30,
            processed_items=20,
            total_items=80,
        )

    stored = await load_job(job_id)
    assert stored.lease_expires_at == NOW + timedelta(seconds=80)
    assert stored.progress == stored.processed_items == 70
    assert stored.total_items == 100
    assert stored.request_count == 2
    assert stored.bytes_received == 1024
    assert stored.stage == JobStage.PROCESSING


async def test_stale_recovery_requeues_fails_and_cancels(db: AsyncSession) -> None:
    expired = NOW - timedelta(seconds=1)
    async with db.begin():
        retry_worker = await add_worker(db, "stale-retry-worker")
        failed_worker = await add_worker(db, "stale-failed-worker")
        cancelled_worker = await add_worker(db, "stale-cancelled-worker")
        retry_job = await add_job(
            db,
            status=JobStatus.RUNNING,
            claimed_by=retry_worker,
            lease_expires_at=expired,
            attempt=1,
            max_attempts=3,
        )
        failed_job = await add_job(
            db,
            status=JobStatus.RUNNING,
            claimed_by=failed_worker,
            lease_expires_at=expired,
            attempt=3,
            max_attempts=3,
        )
        cancelled_job = await add_job(
            db,
            status=JobStatus.RUNNING,
            claimed_by=cancelled_worker,
            lease_expires_at=expired,
            attempt=1,
            cancellation_requested_at=expired,
        )
    async with db.begin():
        recovered = await recover_stale_jobs(db, now=NOW, retry_delay_seconds=30)

    assert retry_job in recovered.requeued_job_ids
    assert failed_job in recovered.failed_job_ids
    assert cancelled_job in recovered.cancelled_job_ids
    assert (await load_job(retry_job)).status == JobStatus.QUEUED
    assert (await load_job(failed_job)).status == JobStatus.FAILED
    assert (await load_job(cancelled_job)).status == JobStatus.CANCELLED


async def test_cancellation_and_worker_stop_are_idempotent(db: AsyncSession) -> None:
    async with db.begin():
        worker_id = await add_worker(db, "stopping-worker")
        job_id = await add_job(db)
    async with db.begin():
        first = await request_job_cancellation(db, job_id=job_id, now=NOW)
        second = await request_job_cancellation(db, job_id=job_id, now=NOW + timedelta(seconds=1))
        assert first is second
        await heartbeat_worker_instance(db, worker_id=worker_id, now=NOW + timedelta(seconds=1))
        stopped = await stop_worker_instance(
            db, worker_id=worker_id, now=NOW + timedelta(seconds=2)
        )
        stopped_again = await stop_worker_instance(
            db, worker_id=worker_id, now=NOW + timedelta(seconds=3)
        )
        assert stopped is not None
        assert stopped is stopped_again
        assert stopped.stopped_at == NOW + timedelta(seconds=2)

    stored = await load_job(job_id)
    assert stored.status == JobStatus.CANCELLED
    async with SessionFactory() as session:
        event_count = await session.scalar(
            select(func.count()).select_from(JobEvent).where(JobEvent.job_id == job_id)
        )
        worker = await heartbeat_worker_instance(
            session, worker_id=worker_id, now=NOW + timedelta(seconds=4)
        )
        assert event_count == 2
        assert worker is None
        stopped_record = await session.get(WorkerInstance, worker_id)
        assert stopped_record is not None
        assert stopped_record.status == WorkerInstanceStatus.STOPPED
