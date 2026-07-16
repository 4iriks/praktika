from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from conftest import csrf_header, login
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.enums import (
    JobEventLevel,
    JobStage,
    JobStatus,
    JobType,
    SourceSyncMode,
    WorkerInstanceStatus,
)
from app.db.models.content import Document
from app.db.models.operations import Job, JobEvent, Source, SourceSyncState, WorkerInstance
from app.db.repositories.jobs import (
    add_job_event,
    claim_next_job,
    complete_job,
    register_worker_instance,
    request_job_cancellation,
)
from app.db.session import SessionFactory
from app.workers.runner import WorkerRunner
from app.workers.source_sync import SourceSyncHandler

pytestmark = pytest.mark.integration
NOW = datetime(2026, 7, 16, 16, tzinfo=UTC)


def worker_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "APP_ENV": "test",
        "APP_VERSION": "0.5.0",
        "STACKEXCHANGE_REQUESTS_PER_SECOND": 10,
        "STACKEXCHANGE_QUOTA_RESERVE": 1,
        "STACKEXCHANGE_MAX_RETRIES": 0,
        "WORKER_HEARTBEAT_SECONDS": 2,
        "WORKER_LEASE_SECONDS": 15,
    }
    values.update(overrides)
    return Settings(
        **values,
    )


async def prepare_dry_run(
    db: AsyncSession,
    *,
    cancellation_requested: bool = False,
) -> tuple[Source, Job, WorkerInstance]:
    source = await db.scalar(select(Source).order_by(Source.id))
    assert source is not None
    active = (
        await db.scalars(
            select(Job).where(
                Job.source_id == source.id,
                Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            )
        )
    ).all()
    for existing in active:
        existing.status = JobStatus.CANCELLED
        existing.cancellable = False
        existing.finished_at = NOW
    source.current_job_id = None
    source.status = "IDLE"
    worker = await register_worker_instance(
        db,
        name="Stage 5 test worker",
        instance_id=f"stage5-worker-{cancellation_requested}",
        capabilities={"source_sync"},
        version="0.5.0",
        hostname="test-host",
        pid=505,
        now=NOW,
    )
    job = Job(
        type=JobType.SOURCE_SYNC,
        status=JobStatus.QUEUED,
        stage=JobStage.PREPARING,
        source_id=source.id,
        total_items=2,
        max_attempts=3,
        payload={
            "sourceId": str(source.id),
            "mode": SourceSyncMode.INITIAL,
            "maxDocuments": 2,
            "maxPages": 1,
            "dryRun": True,
        },
    )
    db.add(job)
    await db.flush()
    claimed = await claim_next_job(
        db,
        worker_id=worker.id,
        supported_types={JobType.SOURCE_SYNC},
        lease_seconds=60,
        now=NOW,
    )
    assert claimed is not None and claimed.id == job.id
    if cancellation_requested:
        await request_job_cancellation(db, job_id=job.id, now=NOW + timedelta(seconds=1))
    return source, job, worker


async def queue_runner_job(
    db: AsyncSession,
    *,
    dry_run: bool,
) -> tuple[Source, Job]:
    source = await db.scalar(select(Source).order_by(Source.id))
    assert source is not None
    active = (
        await db.scalars(
            select(Job).where(
                Job.source_id == source.id,
                Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            )
        )
    ).all()
    for existing in active:
        existing.status = JobStatus.CANCELLED
        existing.cancellable = False
        existing.finished_at = NOW
    source.current_job_id = None
    source.status = "IDLE"
    job = Job(
        type=JobType.SOURCE_SYNC,
        status=JobStatus.QUEUED,
        stage=JobStage.PREPARING,
        source_id=source.id,
        total_items=1,
        max_attempts=3,
        payload={
            "sourceId": str(source.id),
            "mode": SourceSyncMode.INITIAL,
            "maxDocuments": 1,
            "maxPages": 1,
            "dryRun": dry_run,
        },
    )
    db.add(job)
    await db.flush()
    return source, job


async def test_dry_run_worker_saves_checkpoint_events_and_no_documents(
    db: AsyncSession,
) -> None:
    before_documents = await db.scalar(select(func.count()).select_from(Document))
    await db.rollback()
    async with db.begin():
        source, job, worker = await prepare_dry_run(db)

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/answers"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "answer_id": 11,
                            "question_id": 1,
                            "creation_date": 1_700_000_200,
                            "last_activity_date": 1_700_000_300,
                        }
                    ],
                    "has_more": False,
                    "quota_max": 300,
                    "quota_remaining": 250,
                },
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "question_id": 1,
                        "creation_date": 1_700_000_000,
                        "last_activity_date": 1_700_000_100,
                    }
                ],
                "has_more": False,
                "quota_max": 300,
                "quota_remaining": 251,
            },
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        outcome = await SourceSyncHandler(
            session_factory=SessionFactory,
            settings=worker_settings(),
            http_client=http_client,
            job_id=job.id,
            worker_id=worker.id,
            shutdown_requested=asyncio.Event(),
        ).run()
    assert outcome.disposition == "COMPLETED"
    async with SessionFactory() as session, session.begin():
        completed = await complete_job(
            session,
            job_id=job.id,
            worker_id=worker.id,
            result=outcome.result,
        )
        assert completed is not None

    async with SessionFactory() as session:
        stored_job = await session.get(Job, job.id)
        stored_source = await session.get(Source, source.id)
        sync_state = await session.get(SourceSyncState, source.id)
        event_codes = (
            await session.scalars(
                select(JobEvent.code).where(JobEvent.job_id == job.id).order_by(JobEvent.created_at)
            )
        ).all()
        after_documents = await session.scalar(select(func.count()).select_from(Document))
    assert stored_job is not None and stored_source is not None
    assert stored_job.status == JobStatus.COMPLETED
    assert stored_job.checkpoint["dryRun"] is True
    assert stored_job.request_count == 2
    assert stored_job.bytes_received > 0
    assert stored_source.rate_limit_remaining == 250
    assert sync_state is None or sync_state.initial_sync_completed_at is None
    assert before_documents == after_documents
    assert [request.url.path for request in requests] == [
        "/2.3/questions",
        "/2.3/questions/1/answers",
    ]
    assert {
        "JOB_CLAIMED",
        "DRY_RUN_SYNC_STARTED",
        "QUESTIONS_PAGE_FETCHED",
        "ANSWERS_BATCH_FETCHED",
        "CHECKPOINT_SAVED",
        "JOB_COMPLETED",
    }.issubset(event_codes)


async def test_worker_honours_cooperative_cancellation_before_http(
    db: AsyncSession,
) -> None:
    async with db.begin():
        _, job, worker = await prepare_dry_run(db, cancellation_requested=True)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        outcome = await SourceSyncHandler(
            session_factory=SessionFactory,
            settings=worker_settings(),
            http_client=http_client,
            job_id=job.id,
            worker_id=worker.id,
            shutdown_requested=asyncio.Event(),
        ).run()
    assert outcome.disposition == "CANCELLED"
    assert calls == 0


async def test_runner_process_once_completes_dry_run_and_stops_worker(
    db: AsyncSession,
) -> None:
    async with db.begin():
        source, job = await queue_runner_job(db, dry_run=True)

    def handler(request: httpx.Request) -> httpx.Response:
        item_key = "answers" if request.url.path.endswith("/answers") else "questions"
        items: list[dict[str, object]]
        if item_key == "answers":
            items = []
        else:
            items = [
                {
                    "question_id": 501,
                    "creation_date": 1_700_000_000,
                    "last_activity_date": 1_700_000_100,
                }
            ]
        return httpx.Response(
            200,
            json={
                "items": items,
                "has_more": False,
                "quota_max": 300,
                "quota_remaining": 250,
            },
            request=request,
        )

    runner = WorkerRunner(
        session_factory=SessionFactory,
        settings=worker_settings(),
        instance_id="process-once-worker",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        processed = await runner.process_once(http_client)
    assert processed == job.id
    await runner.close()

    async with SessionFactory() as session:
        stored = await session.get(Job, job.id)
        stored_source = await session.get(Source, source.id)
        worker = await session.get(WorkerInstance, runner.worker_id)
    assert stored is not None and stored.status == JobStatus.COMPLETED
    assert stored_source is not None and stored_source.status == "IDLE"
    assert worker is not None and worker.status == WorkerInstanceStatus.STOPPED
    assert worker.current_job_id is None


async def test_runner_marks_unready_non_dry_handler_failed(db: AsyncSession) -> None:
    async with db.begin():
        source, job = await queue_runner_job(db, dry_run=False)
    runner = WorkerRunner(
        session_factory=SessionFactory,
        settings=worker_settings(),
        instance_id="not-ready-worker",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: None)) as client:
        assert await runner.process_once(client) == job.id
    await runner.close()
    async with SessionFactory() as session:
        stored = await session.get(Job, job.id)
        stored_source = await session.get(Source, source.id)
    assert stored is not None and stored.status == JobStatus.FAILED
    assert stored.error_code == "HANDLER_NOT_READY"
    assert stored_source is not None and stored_source.status == "ERROR"


async def test_idle_runner_heartbeats_and_shuts_down_gracefully(db: AsyncSession) -> None:
    async with db.begin():
        source = await db.scalar(select(Source).order_by(Source.id))
        assert source is not None
        jobs = (await db.scalars(select(Job).where(Job.type == JobType.SOURCE_SYNC))).all()
        for job in jobs:
            job.status = JobStatus.CANCELLED
            job.cancellable = False
            job.finished_at = NOW
        source.current_job_id = None
        source.status = "IDLE"

    runner = WorkerRunner(
        session_factory=SessionFactory,
        settings=worker_settings(WORKER_POLL_INTERVAL_SECONDS=0.01),
        instance_id="idle-lifecycle-worker",
    )
    task = asyncio.create_task(runner.run())
    await asyncio.sleep(0.05)
    runner.request_shutdown()
    await asyncio.wait_for(task, timeout=2)
    async with SessionFactory() as session:
        worker = await session.get(WorkerInstance, runner.worker_id)
    assert worker is not None
    assert worker.status == WorkerInstanceStatus.STOPPED
    assert worker.heartbeat_at >= worker.started_at


async def test_sync_api_body_state_events_and_rbac(
    client: httpx.AsyncClient,
    db: AsyncSession,
) -> None:
    await login(client)
    denied_user = await client.post(
        "/api/admin/sources/00000000-0000-0000-0000-000000000000/sync",
        json={"dryRun": True},
        headers=csrf_header(client),
    )
    assert denied_user.status_code == 403

    client.cookies.clear()
    await login(client, "editor@pyanswer.local")
    denied_editor = await client.post(
        "/api/admin/sources/00000000-0000-0000-0000-000000000000/sync",
        json={"dryRun": True},
        headers=csrf_header(client),
    )
    assert denied_editor.status_code == 403

    client.cookies.clear()
    await login(client, "admin@pyanswer.local")
    source = (await client.get("/api/admin/sources")).json()["items"][0]
    await client.post(
        f"/api/admin/sources/{source['id']}/stop",
        headers=csrf_header(client),
    )
    started = await client.post(
        f"/api/admin/sources/{source['id']}/sync",
        json={
            "mode": "INITIAL",
            "maxDocuments": 17,
            "maxPages": 2,
            "dryRun": True,
        },
        headers=csrf_header(client),
    )
    assert started.status_code == 200, started.text
    job_id = started.json()["id"]
    job = await db.get(Job, job_id)
    assert job is not None
    assert job.payload == {
        "sourceId": source["id"],
        "mode": "INITIAL",
        "maxDocuments": 17,
        "maxPages": 2,
        "dryRun": True,
    }
    state = await client.get(f"/api/admin/sources/{source['id']}/sync-state")
    assert state.status_code == 200
    assert state.json()["initialSyncCompletedAt"] is None

    await add_job_event(
        db,
        job_id=job.id,
        level=JobEventLevel.INFO,
        stage=JobStage.PREPARING,
        code="SYNC_REQUESTED",
        message="Dry-run ожидает worker",
    )
    await db.commit()
    admin_events = await client.get(f"/api/admin/jobs/{job_id}/events")
    assert admin_events.status_code == 200
    assert admin_events.json()["items"][0]["code"] == "SYNC_REQUESTED"

    client.cookies.clear()
    await login(client, "editor@pyanswer.local")
    editor_events = await client.get(f"/api/editor/jobs/{job_id}/events")
    assert editor_events.status_code == 200

    client.cookies.clear()
    await login(client)
    assert (await client.get(f"/api/editor/jobs/{job_id}/events")).status_code == 403


async def test_system_worker_status_uses_heartbeat(
    client: httpx.AsyncClient,
    db: AsyncSession,
) -> None:
    await login(client, "admin@pyanswer.local")
    offline = await client.get("/api/admin/system")
    services = {item["id"]: item for item in offline.json()["services"]}
    assert services["crawler"]["status"] == "OFFLINE"
    assert services["qdrant"]["status"] == "OFFLINE"
    assert services["ollama"]["status"] == "OFFLINE"

    now = datetime.now(UTC)
    async with db.begin():
        worker = WorkerInstance(
            name="Online worker",
            instance_id="online-system-worker",
            capabilities=["source_sync"],
            version="0.5.0",
            hostname="test-host",
            pid=506,
            status=WorkerInstanceStatus.RUNNING,
            started_at=now,
            heartbeat_at=now,
        )
        db.add(worker)
    online = await client.get("/api/admin/system")
    services = {item["id"]: item for item in online.json()["services"]}
    assert services["crawler"]["status"] == "ONLINE"
    assert services["crawler"]["version"] == "0.5.0"
