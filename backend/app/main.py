from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import install_error_handlers
from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.csrf import CSRFMiddleware
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()
    configure_logging()
    docs_url = "/api/docs" if config.docs_enabled and config.app_env != "production" else None
    openapi_url = "/api/openapi.json" if docs_url else None
    app = FastAPI(
        title=config.app_name,
        version=config.app_version,
        description=(
            "Серверный API PyAnswer. Cookie-auth endpoints требуют CSRF для unsafe methods. "
            "Search/RAG будут подключены на Этапе 6."
        ),
        docs_url=docs_url,
        openapi_url=openapi_url,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.frontend_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", "X-CSRF-Token", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(CSRFMiddleware, settings=config)
    app.add_middleware(RequestContextMiddleware, settings=config)
    install_error_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
