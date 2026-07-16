from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.enums import JobStage, JobStatus, JobType, SourceSyncMode
from app.db.models.content import Document
from app.db.models.operations import (
    IngestionFailure,
    Job,
    Source,
    SourceSyncState,
    WorkerInstance,
)
from app.db.repositories.jobs import (
    claim_next_job,
    register_worker_instance,
    request_job_cancellation,
)
from app.db.session import SessionFactory
from app.workers.runner import WorkerRunner
from app.workers.source_sync import SourceSyncHandler

pytestmark = pytest.mark.integration
NOW = datetime(2026, 7, 16, 20, tzinfo=UTC)


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "APP_ENV": "test",
        "STACKEXCHANGE_REQUESTS_PER_SECOND": 10,
        "STACKEXCHANGE_QUOTA_RESERVE": 1,
        "STACKEXCHANGE_MAX_RETRIES": 0,
        "STACKEXCHANGE_MAX_PAGES": 10,
        "MIN_QUESTION_TEXT_LENGTH": 10,
        "MIN_ANSWER_TEXT_LENGTH": 1,
        "CHUNK_TARGET_TOKENS": 50,
        "CHUNK_MAX_TOKENS": 100,
        "CHUNK_OVERLAP_TOKENS": 5,
        "CHUNK_MIN_TOKENS": 3,
    }
    values.update(overrides)
    return Settings(**values)


async def prepare_source(db: AsyncSession) -> Source:
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
    for job in active:
        job.status = JobStatus.CANCELLED
        job.cancellable = False
        job.finished_at = NOW
    source.current_job_id = None
    source.status = "IDLE"
    return source


async def enqueue(
    db: AsyncSession,
    source: Source,
    *,
    mode: SourceSyncMode,
    max_documents: int,
    max_pages: int = 2,
) -> Job:
    job = Job(
        type=JobType.SOURCE_SYNC,
        status=JobStatus.QUEUED,
        stage=JobStage.PREPARING,
        source_id=source.id,
        total_items=max_documents,
        max_attempts=3,
        payload={
            "sourceId": str(source.id),
            "mode": mode.value,
            "maxDocuments": max_documents,
            "maxPages": max_pages,
            "dryRun": False,
        },
    )
    db.add(job)
    await db.flush()
    return job


def question_item(question_id: int, *, body: str | None = None) -> dict[str, object]:
    return {
        "question_id": question_id,
        "title": f"Вопрос Python {question_id}",
        "body": body or "<p>Как обработать документ безопасно и детерминированно?</p>",
        "tags": ["python", "postgresql"],
        "link": f"https://ru.stackoverflow.com/questions/{question_id}/example",
        "creation_date": 1_700_000_000 + question_id,
        "last_activity_date": 1_700_001_000 + question_id,
        "answer_count": 1,
        "accepted_answer_id": question_id + 10_000,
        "is_answered": True,
    }


def answer_item(question_id: int) -> dict[str, object]:
    return {
        "answer_id": question_id + 10_000,
        "question_id": question_id,
        "body": "<p>Используйте короткую транзакцию и повторяемый upsert.</p>",
        "creation_date": 1_700_000_500 + question_id,
        "last_activity_date": 1_700_001_000 + question_id,
        "score": 5,
        "is_accepted": True,
    }


def corpus_transport(question_ids: list[int]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/answers"):
            requested_ids = {int(value) for value in request.url.path.split("/")[-2].split(";")}
            items = [answer_item(item) for item in question_ids if item in requested_ids]
        else:
            items = [question_item(item) for item in question_ids]
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

    return httpx.MockTransport(handler)


async def run_queued(job_id: UUID, transport: httpx.MockTransport, instance: str) -> None:
    runner = WorkerRunner(
        session_factory=SessionFactory,
        settings=settings(),
        instance_id=instance,
    )
    async with httpx.AsyncClient(transport=transport) as client:
        assert await runner.process_once(client) == job_id
    await runner.close()


async def test_capped_initial_sync_resumes_inside_page_and_completes(
    db: AsyncSession,
) -> None:
    async with db.begin():
        source = await prepare_source(db)
        first = await enqueue(db, source, mode=SourceSyncMode.INITIAL, max_documents=1)
    transport = corpus_transport([801_001, 801_002])
    await run_queued(first.id, transport, "initial-page-part-1")

    async with SessionFactory() as session:
        stored_first = await session.get(Job, first.id)
        state = await session.get(SourceSyncState, source.id)
        assert stored_first is not None and state is not None
        assert stored_first.result["syncComplete"] is False
        assert stored_first.checkpoint["currentPage"] == 1
        assert stored_first.checkpoint["itemOffset"] == 1
        assert state.initial_sync_completed_at is None

    async with SessionFactory() as session, session.begin():
        stored_source = await session.get(Source, source.id)
        assert stored_source is not None
        second = await enqueue(
            session,
            stored_source,
            mode=SourceSyncMode.AUTO,
            max_documents=1,
        )
    await run_queued(second.id, transport, "initial-page-part-2")

    async with SessionFactory() as session:
        state = await session.get(SourceSyncState, source.id)
        count = await session.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.external_id.in_(["801001", "801002"]))
        )
        second_job = await session.get(Job, second.id)
    assert count == 2
    assert second_job is not None and second_job.result["syncComplete"] is True
    assert state is not None and state.initial_sync_completed_at is not None
    assert state.next_page == 1 and state.current_mode is None


async def test_incremental_uses_watermark_overlap_and_advances_only_on_success(
    db: AsyncSession,
) -> None:
    watermark = NOW - timedelta(days=2)
    async with db.begin():
        source = await prepare_source(db)
        db.add(
            SourceSyncState(
                source_id=source.id,
                initial_sync_completed_at=NOW - timedelta(days=10),
                incremental_watermark=watermark,
                next_page=1,
                state={},
            )
        )
        job = await enqueue(db, source, mode=SourceSyncMode.AUTO, max_documents=10)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"items": [], "has_more": False, "quota_remaining": 250},
            request=request,
        )

    runner = WorkerRunner(
        session_factory=SessionFactory,
        settings=settings(STACKEXCHANGE_INCREMENTAL_OVERLAP_SECONDS=3600),
        instance_id="incremental-success",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await runner.process_once(client) == job.id
    await runner.close()

    assert requests[0].url.params["sort"] == "activity"
    assert int(requests[0].url.params["fromdate"]) == round(watermark.timestamp()) - 3600
    async with SessionFactory() as session:
        state = await session.get(SourceSyncState, source.id)
        stored_job = await session.get(Job, job.id)
    assert state is not None and stored_job is not None
    assert state.incremental_watermark is not None
    assert state.incremental_watermark > watermark
    assert stored_job.status == JobStatus.COMPLETED


async def test_invalid_api_schema_fails_without_advancing_incremental_watermark(
    db: AsyncSession,
) -> None:
    watermark = NOW - timedelta(days=1)
    async with db.begin():
        source = await prepare_source(db)
        db.add(
            SourceSyncState(
                source_id=source.id,
                initial_sync_completed_at=NOW - timedelta(days=10),
                incremental_watermark=watermark,
                next_page=1,
                state={},
            )
        )
        job = await enqueue(db, source, mode=SourceSyncMode.INCREMENTAL, max_documents=10)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b'{"items":[{"question_id":', request=request)

    runner = WorkerRunner(
        session_factory=SessionFactory,
        settings=settings(),
        instance_id="incremental-invalid-schema",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await runner.process_once(client) == job.id
    await runner.close()
    async with SessionFactory() as session:
        state = await session.get(SourceSyncState, source.id)
        stored_job = await session.get(Job, job.id)
    assert stored_job is not None and stored_job.status == JobStatus.FAILED
    assert stored_job.error_code == "STACKEXCHANGE_INVALID_RESPONSE"
    assert state is not None and state.incremental_watermark == watermark


async def test_invalid_question_is_isolated_and_other_document_commits(
    db: AsyncSession,
) -> None:
    async with db.begin():
        source = await prepare_source(db)
        job = await enqueue(db, source, mode=SourceSyncMode.INITIAL, max_documents=2)

    def handler(request: httpx.Request) -> httpx.Response:
        items: list[dict[str, object]]
        if request.url.path.endswith("/answers"):
            items = []
        else:
            items = [
                question_item(802_001, body="<p>x</p>"),
                question_item(802_002),
            ]
        return httpx.Response(
            200,
            json={"items": items, "has_more": False, "quota_remaining": 250},
            request=request,
        )

    await run_queued(job.id, httpx.MockTransport(handler), "failure-isolation")
    async with SessionFactory() as session:
        stored_job = await session.get(Job, job.id)
        good = await session.scalar(select(Document).where(Document.external_id == "802002"))
        bad = await session.scalar(select(Document).where(Document.external_id == "802001"))
        failure = await session.scalar(
            select(IngestionFailure).where(IngestionFailure.external_id == "802001")
        )
    assert stored_job is not None and stored_job.status == JobStatus.COMPLETED
    assert stored_job.result["skipped"] == 1
    assert good is not None and bad is None
    assert failure is not None and failure.error_code == "QUESTION_TOO_SHORT"
    assert good.bm25_status == good.vector_status == "NOT_INDEXED"


async def test_cancellation_keeps_last_completed_page_checkpoint(db: AsyncSession) -> None:
    async with db.begin():
        source = await prepare_source(db)
        worker: WorkerInstance = await register_worker_instance(
            db,
            name="Cancellation worker",
            instance_id="pipeline-cancellation",
            capabilities={"source_sync"},
            version="0.5.0",
            hostname="test",
            pid=505,
            now=NOW,
        )
        job = await enqueue(
            db,
            source,
            mode=SourceSyncMode.INITIAL,
            max_documents=2,
            max_pages=2,
        )
        claimed = await claim_next_job(
            db,
            worker_id=worker.id,
            supported_types={JobType.SOURCE_SYNC},
            lease_seconds=60,
            now=NOW,
        )
        assert claimed is not None

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/answers"):
            question_id = int(request.url.path.split("/")[-2])
            items: list[dict[str, object]] = [answer_item(question_id)]
            has_more = False
        else:
            page = int(request.url.params["page"])
            if page == 2:
                async with SessionFactory() as session, session.begin():
                    await request_job_cancellation(session, job_id=job.id)
            items = [question_item(803_000 + page)]
            has_more = page == 1
        return httpx.Response(
            200,
            json={"items": items, "has_more": has_more, "quota_remaining": 250},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        outcome = await SourceSyncHandler(
            session_factory=SessionFactory,
            settings=settings(),
            http_client=client,
            job_id=job.id,
            worker_id=worker.id,
            shutdown_requested=asyncio.Event(),
        ).run()
    async with SessionFactory() as session:
        stored = await session.get(Job, job.id)
        first_document = await session.scalar(
            select(Document).where(Document.external_id == "803001")
        )
        second_document = await session.scalar(
            select(Document).where(Document.external_id == "803002")
        )
    assert outcome.disposition == "CANCELLED"
    assert stored is not None and stored.checkpoint["currentPage"] == 2
    assert first_document is not None and second_document is None
