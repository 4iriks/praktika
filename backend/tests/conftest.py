from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import command

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
if "test" not in TEST_DATABASE_URL.casefold():
    raise RuntimeError(
        "Integration tests require TEST_DATABASE_URL pointing to a disposable test database"
    )

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["TEST_DATABASE_URL"] = TEST_DATABASE_URL
os.environ["APP_ENV"] = "test"
os.environ["ARGON2_TIME_COST"] = "1"
os.environ["ARGON2_MEMORY_COST"] = "8192"
os.environ["ARGON2_PARALLELISM"] = "1"
os.environ["SEED_DEMO_DATA"] = "true"

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.db.base import Base  # noqa: E402
from app.db.session import SessionFactory, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed.demo import seed_demo_data  # noqa: E402

DEMO_PASSWORD = "Demo123!"


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> Iterator[None]:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    yield


@pytest_asyncio.fixture(autouse=True)
async def reset_database(
    migrated_database: None, request: pytest.FixtureRequest
) -> AsyncIterator[None]:
    if request.node.get_closest_marker("integration") is None:
        yield
        return
    table_names = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))
    async with SessionFactory() as session:
        async with session.begin():
            await seed_demo_data(session, get_settings())
    yield


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as value:
        yield value


@pytest_asyncio.fixture
async def db() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session


async def csrf(client: AsyncClient) -> str:
    response = await client.get("/api/auth/csrf")
    assert response.status_code == 200
    return response.json()["csrfToken"]


async def login(
    client: AsyncClient,
    email: str = "user@pyanswer.local",
    password: str = DEMO_PASSWORD,
) -> dict[str, object]:
    token = await csrf(client)
    response = await client.post(
        "/api/auth/login",
        json={"email": email, "password": password, "remember": False},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200, response.text
    return response.json()


def csrf_header(client: AsyncClient) -> dict[str, str]:
    token = client.cookies.get("pyanswer_csrf")
    assert token
    return {"X-CSRF-Token": token}
