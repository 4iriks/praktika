from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from conftest import csrf, csrf_header, login
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.db.session import get_db_session
from app.main import app, create_app

pytestmark = pytest.mark.integration


async def test_live_ready_docs_and_public_status(client: AsyncClient) -> None:
    live = await client.get("/api/health/live")
    ready = await client.get("/api/health/ready")
    docs = await client.get("/api/docs")
    status = await client.get("/api/status")

    assert live.json() == {"status": "ok"}
    assert ready.json() == {"status": "ready"}
    assert docs.status_code == 200 and "swagger-ui" in docs.text
    assert status.status_code == 200
    assert status.json()["indexedDocuments"] == 20
    service_states = {item["name"]: item["state"] for item in status.json()["services"]}
    assert service_states["PostgreSQL"] == "online"
    assert service_states["Qdrant"] == "offline"


async def test_ready_returns_503_when_database_is_unavailable(client: AsyncClient) -> None:
    class OfflineSession:
        async def execute(self, statement: object) -> None:
            raise SQLAlchemyError("offline")

    async def offline_database() -> AsyncIterator[OfflineSession]:
        yield OfflineSession()

    app.dependency_overrides[get_db_session] = offline_database
    try:
        response = await client.get("/api/health/ready")
    finally:
        app.dependency_overrides.pop(get_db_session, None)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


async def test_search_and_rag_require_active_index(
    client: AsyncClient,
) -> None:
    search = await client.get("/api/search", params={"q": "asyncio"})
    assert search.status_code == 503
    assert search.json()["error"]["code"] == "SERVICE_UNAVAILABLE"

    token = await csrf(client)
    ask = await client.post(
        "/api/ask",
        json={"question": "Что такое asyncio?", "mode": "hybrid"},
        headers={"X-CSRF-Token": token},
    )
    assert ask.status_code == 503
    assert ask.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


async def test_guest_search_and_rag_settings_are_enforced(client: AsyncClient) -> None:
    await login(client, "admin@pyanswer.local")
    updated = await client.patch(
        "/api/admin/system/settings",
        json={"allowGuestSearch": False, "allowGuestRag": False},
        headers=csrf_header(client),
    )
    assert updated.status_code == 200
    client.cookies.clear()

    search = await client.get("/api/search?q=python")
    token = await csrf(client)
    ask = await client.post(
        "/api/ask",
        json={"question": "Python?", "mode": "bm25"},
        headers={"X-CSRF-Token": token},
    )
    assert search.status_code == ask.status_code == 401


async def test_openapi_has_required_routes_operation_ids_and_camel_case(
    client: AsyncClient,
) -> None:
    schema = (await client.get("/api/openapi.json")).json()
    required = {
        "/api/auth/register",
        "/api/auth/login",
        "/api/auth/logout",
        "/api/users/me",
        "/api/history",
        "/api/saved/{document_id}",
        "/api/feedback",
        "/api/editor/documents",
        "/api/admin/users",
        "/api/admin/sources",
        "/api/admin/jobs",
        "/api/admin/audit",
        "/api/admin/system/settings",
        "/api/search",
        "/api/ask",
        "/api/ask/stream",
    }
    assert required <= schema["paths"].keys()
    assert schema["paths"]["/api/auth/login"]["post"]["operationId"] == "login"

    await login(client)
    profile = (await client.get("/api/users/me")).json()
    assert "displayName" in profile and "display_name" not in profile
    assert "accountStatus" in profile


async def test_pagination_and_sort_contract(client: AsyncClient) -> None:
    await login(client, "admin@pyanswer.local")
    response = await client.get("/api/admin/users", params={"page": 2, "limit": 5})
    assert response.status_code == 200
    assert response.json()["pagination"] == {
        "page": 2,
        "pageSize": 5,
        "total": 13,
        "totalPages": 3,
    }
    assert (await client.get("/api/admin/users?sort=drop-table")).status_code == 422


async def test_sql_dashboards_return_aggregated_metrics(client: AsyncClient) -> None:
    await login(client, "admin@pyanswer.local")
    admin = await client.get("/api/admin/dashboard")
    editor = await client.get("/api/editor/dashboard")
    assert admin.status_code == editor.status_code == 200
    assert admin.json()["totalUsers"] == 13
    assert admin.json()["documentsCount"] == 20
    assert admin.json()["chunksCount"] > 0
    assert admin.json()["popularTags"]
    assert editor.json()["statusCounts"]["HIDDEN"] == 1


async def test_production_errors_do_not_expose_tracebacks() -> None:
    settings = Settings(
        APP_ENV="production",
        DATABASE_URL="postgresql+asyncpg://safe:placeholder@localhost/pyanswer",
        COOKIE_SECURE=True,
        DOCS_ENABLED=False,
        SEED_DEMO_DATA=False,
    )
    test_app: FastAPI = create_app(settings)

    async def explode() -> None:
        raise RuntimeError("sensitive-internal-detail")

    test_app.add_api_route("/explode", explode, methods=["GET"])
    transport = ASGITransport(app=test_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="https://testserver") as value:
        response = await value.get("/explode")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "sensitive-internal-detail" not in response.text
    assert "traceback" not in response.text.casefold()
