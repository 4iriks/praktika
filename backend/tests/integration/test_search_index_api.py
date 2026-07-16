from __future__ import annotations

import pytest
from conftest import csrf_header, login
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import JobStatus, JobType
from app.db.models.operations import Job, SearchIndexEntry, SearchIndexVersion

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    ("email", "expected"),
    [
        ("user@pyanswer.local", 403),
        ("editor@pyanswer.local", 403),
        ("admin@pyanswer.local", 200),
    ],
)
async def test_index_routes_are_server_authorized(
    client: AsyncClient, email: str, expected: int
) -> None:
    await login(client, email)
    response = await client.get("/api/admin/indexes")
    assert response.status_code == expected
    if expected == 200:
        assert response.json()["pagination"] == {
            "page": 1,
            "pageSize": 20,
            "total": 0,
            "totalPages": 1,
        }


async def test_admin_enqueues_only_one_full_reindex(client: AsyncClient, db: AsyncSession) -> None:
    await login(client, "admin@pyanswer.local")
    missing_confirmation = await client.post(
        "/api/admin/indexes/full-reindex",
        json={"confirm": False},
        headers=csrf_header(client),
    )
    assert missing_confirmation.status_code == 422
    created = await client.post(
        "/api/admin/indexes/full-reindex",
        json={"confirm": True},
        headers=csrf_header(client),
    )
    assert created.status_code == 200, created.text
    assert created.json()["type"] == JobType.FULL_REINDEX
    duplicate = await client.post(
        "/api/admin/indexes/full-reindex",
        json={"confirm": True},
        headers=csrf_header(client),
    )
    assert duplicate.status_code == 409
    count = await db.scalar(
        select(func.count())
        .select_from(Job)
        .where(
            Job.type == JobType.FULL_REINDEX,
            Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        )
    )
    assert count == 1


async def test_stage6_tables_are_available(db: AsyncSession) -> None:
    assert await db.scalar(select(func.count()).select_from(SearchIndexVersion)) == 0
    assert await db.scalar(select(func.count()).select_from(SearchIndexEntry)) == 0
