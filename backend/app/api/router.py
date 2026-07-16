from fastapi import APIRouter

from app.api.routes import (
    admin_audit,
    admin_indexes,
    admin_ingestion,
    admin_jobs,
    admin_sources,
    admin_system,
    admin_users,
    auth,
    dashboards,
    documents,
    editor,
    feedback,
    health,
    history,
    saved,
    search,
    status,
    users,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(history.router)
api_router.include_router(saved.router)
api_router.include_router(feedback.router)
api_router.include_router(documents.router)
api_router.include_router(search.router)
api_router.include_router(status.router)
api_router.include_router(editor.router)
api_router.include_router(dashboards.router)
api_router.include_router(admin_users.router)
api_router.include_router(admin_sources.router)
api_router.include_router(admin_ingestion.router)
api_router.include_router(admin_indexes.router)
api_router.include_router(admin_jobs.router)
api_router.include_router(admin_audit.router)
api_router.include_router(admin_system.router)
