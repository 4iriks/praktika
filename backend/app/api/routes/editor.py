from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import DB, require_all_permissions, require_permission
from app.api.pagination import parse_optional_datetime
from app.core.enums import Permission
from app.db.models.identity import User
from app.schemas.management import (
    BackgroundJobOut,
    BulkDocumentRequest,
    BulkDocumentResultOut,
    EditorDashboardOut,
    HideDocumentRequest,
    JobsResponse,
    ManagedDocumentDetailOut,
    ManagedDocumentsResponse,
    ManagedDocumentUpdate,
)
from app.services.editor import (
    bulk_documents,
    editor_dashboard,
    get_managed_document,
    hide_document,
    list_jobs,
    list_managed_documents,
    reindex_document,
    restore_document,
    update_metadata,
)

router = APIRouter(prefix="/editor", tags=["editor"])
EditorViewer = Annotated[User, Depends(require_permission(Permission.MANAGED_DOCUMENTS_VIEW))]
MetadataEditor = Annotated[User, Depends(require_permission(Permission.DOCUMENT_METADATA_EDIT))]
StatusEditor = Annotated[User, Depends(require_permission(Permission.DOCUMENT_STATUS_CHANGE))]
ReindexEditor = Annotated[User, Depends(require_permission(Permission.DOCUMENT_REINDEX))]
BulkEditor = Annotated[
    User,
    Depends(
        require_all_permissions(
            Permission.DOCUMENT_STATUS_CHANGE,
            Permission.DOCUMENT_REINDEX,
        )
    ),
]
JobsViewer = Annotated[User, Depends(require_permission(Permission.EDITOR_JOBS_VIEW))]


@router.get(
    "/dashboard",
    response_model=EditorDashboardOut,
    summary="Получить метрики редактора",
    operation_id="getEditorDashboard",
)
async def dashboard(db: DB, actor: EditorViewer) -> EditorDashboardOut:
    return await editor_dashboard(db)


@router.get(
    "/documents",
    response_model=ManagedDocumentsResponse,
    summary="Получить управляемые документы",
    operation_id="getManagedDocuments",
)
async def documents(
    db: DB,
    actor: EditorViewer,
    q: str = "",
    status: str = "ALL",
    tags: str = "",
    accepted: str = "all",
    has_code: str = "all",
    bm25: str = "ALL",
    vector: str = "ALL",
    source: str = "",
    updated_after: str = "",
    sort: str = "updated_desc",
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> ManagedDocumentsResponse:
    return await list_managed_documents(
        db,
        q=q,
        status=status,
        tags=[item for item in tags.split(",") if item],
        accepted=accepted,
        has_code=has_code,
        bm25=bm25,
        vector=vector,
        source=source,
        updated_after=parse_optional_datetime(updated_after),
        sort=sort,
        page=page,
        limit=limit,
    )


@router.post(
    "/documents/bulk",
    response_model=BulkDocumentResultOut,
    summary="Выполнить массовую операцию",
    operation_id="bulkUpdateDocuments",
)
async def bulk(
    payload: BulkDocumentRequest, request: Request, db: DB, actor: BulkEditor
) -> BulkDocumentResultOut:
    return await bulk_documents(db, request, actor, payload)


@router.get(
    "/documents/{document_id}",
    response_model=ManagedDocumentDetailOut,
    summary="Получить документ редактора",
    operation_id="getManagedDocument",
)
async def document_detail(
    document_id: UUID, db: DB, actor: EditorViewer
) -> ManagedDocumentDetailOut:
    return await get_managed_document(db, document_id)


@router.patch(
    "/documents/{document_id}/metadata",
    response_model=ManagedDocumentDetailOut,
    summary="Обновить управленческие метаданные",
    operation_id="updateDocumentMetadata",
)
async def metadata(
    document_id: UUID,
    payload: ManagedDocumentUpdate,
    request: Request,
    db: DB,
    actor: MetadataEditor,
) -> ManagedDocumentDetailOut:
    return await update_metadata(db, request, actor, document_id, payload)


@router.post(
    "/documents/{document_id}/hide",
    response_model=ManagedDocumentDetailOut,
    summary="Скрыть документ",
    operation_id="hideDocument",
)
async def hide(
    document_id: UUID,
    payload: HideDocumentRequest,
    request: Request,
    db: DB,
    actor: StatusEditor,
) -> ManagedDocumentDetailOut:
    return await hide_document(db, request, actor, document_id, payload.reason)


@router.post(
    "/documents/{document_id}/restore",
    response_model=ManagedDocumentDetailOut,
    summary="Восстановить документ",
    operation_id="restoreDocument",
)
async def restore(
    document_id: UUID, request: Request, db: DB, actor: StatusEditor
) -> ManagedDocumentDetailOut:
    return await restore_document(db, request, actor, document_id)


@router.post(
    "/documents/{document_id}/reindex",
    response_model=BackgroundJobOut,
    summary="Создать задание переиндексации",
    operation_id="reindexDocument",
)
async def reindex(
    document_id: UUID, request: Request, db: DB, actor: ReindexEditor
) -> BackgroundJobOut:
    return await reindex_document(db, request, actor, document_id)


@router.get(
    "/jobs",
    response_model=JobsResponse,
    summary="Получить задания редактора",
    operation_id="getEditorJobs",
)
async def jobs(
    db: DB,
    actor: JobsViewer,
    id: str = "",
    type: str = "ALL",
    status: str = "ALL",
    stage: str = "ALL",
    actor_filter: str = Query("", alias="actor"),
    document_id: str = "",
    source: str = "",
    date_from: str = "",
    date_to: str = "",
    sort: str = "created_desc",
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> JobsResponse:
    return await list_jobs(
        db,
        job_id=id,
        type_filter=type,
        status=status,
        stage=stage,
        actor=actor_filter,
        document_id=document_id,
        source=source,
        date_from=parse_optional_datetime(date_from),
        date_to=parse_optional_datetime(date_to),
        sort=sort,
        page=page,
        limit=limit,
    )
