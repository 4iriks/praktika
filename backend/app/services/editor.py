from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from fastapi import Request
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.errors import ApiException
from app.core.enums import (
    AuditAction,
    AuditEntityType,
    DocumentStatus,
    IndexStatus,
    JobStatus,
    JobType,
)
from app.db.base import utc_now
from app.db.models.content import Document, DocumentTag, Tag
from app.db.models.identity import User
from app.db.models.operations import AuditEvent, Job
from app.schemas.base import pagination
from app.schemas.management import (
    BackgroundJobOut,
    BulkDocumentItemOut,
    BulkDocumentRequest,
    BulkDocumentResultOut,
    EditorDashboardOut,
    JobsResponse,
    ManagedDocumentDetailOut,
    ManagedDocumentsResponse,
    ManagedDocumentUpdate,
)
from app.services.audit import add_audit_event
from app.services.content import document_statement, get_document
from app.services.management_serializers import (
    audit_to_schema,
    job_to_schema,
    managed_document_to_schema,
)


async def managed_detail(db: AsyncSession, document: Document) -> ManagedDocumentDetailOut:
    base = await managed_document_to_schema(db, document)
    audit = (
        await db.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.entity_type == AuditEntityType.DOCUMENT,
                AuditEvent.entity_id == str(document.id),
            )
            .order_by(AuditEvent.created_at.desc())
            .limit(30)
        )
    ).all()
    jobs = (
        await db.scalars(
            select(Job)
            .where(Job.document_id == document.id)
            .options(selectinload(Job.creator))
            .order_by(Job.created_at.desc())
            .limit(30)
        )
    ).all()
    return ManagedDocumentDetailOut(
        **base.model_dump(),
        audit_events=[audit_to_schema(item) for item in audit],
        related_jobs=[job_to_schema(item) for item in jobs],
    )


async def get_managed_document(db: AsyncSession, document_id: UUID) -> ManagedDocumentDetailOut:
    return await managed_detail(db, await get_document(db, document_id))


async def list_managed_documents(
    db: AsyncSession,
    *,
    q: str,
    status: str,
    tags: list[str],
    accepted: str,
    has_code: str,
    bm25: str,
    vector: str,
    source: str,
    updated_after: datetime | None,
    sort: str,
    page: int,
    limit: int,
) -> ManagedDocumentsResponse:
    filters = []
    if q:
        filters.append(
            or_(
                Document.normalized_title.ilike(f"%{q}%"),
                Document.external_id.ilike(f"%{q}%"),
            )
        )
    if status != "ALL":
        filters.append(Document.status == status)
    if accepted != "all":
        filters.append(
            Document.accepted_answer_external_id.is_not(None)
            if accepted == "true"
            else Document.accepted_answer_external_id.is_(None)
        )
    if has_code != "all":
        filters.append(Document.has_code.is_(has_code == "true"))
    if bm25 != "ALL":
        filters.append(Document.bm25_status == bm25)
    if vector != "ALL":
        filters.append(Document.vector_status == vector)
    if source:
        filters.append(Document.source_id == UUID(source))
    if updated_after is not None:
        filters.append(Document.updated_at >= updated_after)
    if tags:
        filters.append(
            Document.id.in_(
                select(DocumentTag.document_id)
                .join(Tag, Tag.id == DocumentTag.tag_id)
                .where(Tag.normalized_name.in_(tags))
            )
        )
    total = await db.scalar(select(func.count()).select_from(Document).where(*filters)) or 0
    statement = document_statement().where(*filters)
    if sort == "updated_desc":
        statement = statement.order_by(Document.updated_at.desc(), Document.id)
    elif sort == "updated_asc":
        statement = statement.order_by(Document.updated_at.asc(), Document.id)
    elif sort == "rating_desc":
        statement = statement.order_by(Document.score.desc(), Document.id)
    elif sort == "title_asc":
        statement = statement.order_by(Document.normalized_title.asc(), Document.id)
    elif sort == "status_asc":
        statement = statement.order_by(Document.status.asc(), Document.id)
    else:
        raise ApiException(422, "VALIDATION_ERROR", "Неизвестная сортировка")
    items = (await db.scalars(statement.offset((page - 1) * limit).limit(limit))).unique().all()
    available_tags = (
        await db.scalars(select(Tag.normalized_name).order_by(Tag.normalized_name))
    ).all()
    return ManagedDocumentsResponse(
        items=[await managed_document_to_schema(db, item) for item in items],
        available_tags=list(available_tags),
        pagination=pagination(page, limit, total),
    )


async def replace_managed_tags(db: AsyncSession, document: Document, names: list[str]) -> None:
    await db.execute(
        delete(DocumentTag).where(
            DocumentTag.document_id == document.id,
            DocumentTag.is_managed.is_(True),
        )
    )
    for name in names:
        tag = await db.scalar(select(Tag).where(Tag.normalized_name == name))
        if tag is None:
            tag = Tag(normalized_name=name, display_name=name)
            db.add(tag)
            await db.flush()
        db.add(DocumentTag(document_id=document.id, tag_id=tag.id, is_managed=True))
    await db.flush()
    await db.refresh(document, attribute_names=["tag_links"])


async def update_metadata(
    db: AsyncSession,
    request: Request,
    actor: User,
    document_id: UUID,
    payload: ManagedDocumentUpdate,
) -> ManagedDocumentDetailOut:
    document = await get_document(db, document_id, lock=True)
    before = {
        "normalizedTitle": document.normalized_title,
        "managedTags": [link.tag.normalized_name for link in document.tag_links if link.is_managed],
        "editorialNote": document.editorial_note,
        "version": document.version,
    }
    document.normalized_title = payload.normalized_title
    document.editorial_note = payload.editorial_note
    document.version += 1
    document.last_edited_by = actor.id
    document.last_edited_at = utc_now()
    await replace_managed_tags(db, document, payload.managed_tags)
    await add_audit_event(
        db,
        request,
        actor=actor,
        action=AuditAction.UPDATE_DOCUMENT_METADATA,
        entity_type=AuditEntityType.DOCUMENT,
        entity_id=str(document.id),
        entity_label=document.normalized_title,
        summary="Обновлены управленческие метаданные документа",
        before=before,
        after={
            "normalizedTitle": document.normalized_title,
            "managedTags": payload.managed_tags,
            "editorialNote": document.editorial_note,
            "version": document.version,
        },
    )
    await db.flush()
    return await managed_detail(db, document)


async def hide_document(
    db: AsyncSession,
    request: Request,
    actor: User,
    document_id: UUID,
    reason: str,
) -> ManagedDocumentDetailOut:
    document = await get_document(db, document_id, lock=True)
    if document.status not in {DocumentStatus.ACTIVE, DocumentStatus.OUTDATED}:
        raise ApiException(409, "CONFLICT", "Документ нельзя скрыть в текущем статусе")
    before = document.status
    document.status = DocumentStatus.HIDDEN
    document.hidden_reason = reason.strip()
    document.last_edited_by = actor.id
    document.last_edited_at = utc_now()
    document.version += 1
    await add_audit_event(
        db,
        request,
        actor=actor,
        action=AuditAction.HIDE_DOCUMENT,
        entity_type=AuditEntityType.DOCUMENT,
        entity_id=str(document.id),
        entity_label=document.normalized_title,
        summary="Документ скрыт из пользовательского контура",
        before={"status": before},
        after={"status": document.status, "reason": document.hidden_reason},
    )
    await db.flush()
    return await managed_detail(db, document)


async def restore_document(
    db: AsyncSession, request: Request, actor: User, document_id: UUID
) -> ManagedDocumentDetailOut:
    document = await get_document(db, document_id, lock=True)
    if document.status != DocumentStatus.HIDDEN:
        raise ApiException(409, "CONFLICT", "Восстановить можно только скрытый документ")
    restored = (
        DocumentStatus.OUTDATED
        if IndexStatus.OUTDATED in {document.bm25_status, document.vector_status}
        else DocumentStatus.ACTIVE
    )
    document.status = restored
    document.hidden_reason = None
    document.last_edited_by = actor.id
    document.last_edited_at = utc_now()
    document.version += 1
    await add_audit_event(
        db,
        request,
        actor=actor,
        action=AuditAction.RESTORE_DOCUMENT,
        entity_type=AuditEntityType.DOCUMENT,
        entity_id=str(document.id),
        entity_label=document.normalized_title,
        summary="Документ восстановлен",
        before={"status": DocumentStatus.HIDDEN},
        after={"status": restored},
    )
    await db.flush()
    return await managed_detail(db, document)


async def create_reindex_job(
    db: AsyncSession,
    request: Request,
    actor: User,
    document: Document,
    *,
    batch_id: str | None = None,
    audit: bool = True,
) -> Job:
    job = Job(
        type=JobType.DOCUMENT_REINDEX,
        status=JobStatus.QUEUED,
        stage="PREPARING",
        progress=0,
        total_items=1,
        document_id=document.id,
        source_id=document.source_id,
        created_by=actor.id,
        cancellable=True,
        payload={"documentId": str(document.id)},
    )
    db.add(job)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise ApiException(409, "CONFLICT", "Переиндексация документа уже запущена") from exc
    document.bm25_status = IndexStatus.PENDING
    document.vector_status = IndexStatus.PENDING
    if audit:
        await add_audit_event(
            db,
            request,
            actor=actor,
            action=AuditAction.REINDEX_DOCUMENT,
            entity_type=AuditEntityType.DOCUMENT,
            entity_id=str(document.id),
            entity_label=document.normalized_title,
            summary="Создано задание переиндексации",
            after={"jobId": str(job.id)},
            batch_id=batch_id,
        )
    return job


async def reindex_document(
    db: AsyncSession, request: Request, actor: User, document_id: UUID
) -> BackgroundJobOut:
    document = await get_document(db, document_id, lock=True)
    job = await create_reindex_job(db, request, actor, document)
    await db.refresh(job, attribute_names=["creator"])
    return job_to_schema(job)


async def bulk_documents(
    db: AsyncSession, request: Request, actor: User, payload: BulkDocumentRequest
) -> BulkDocumentResultOut:
    batch_id = uuid4()
    items: list[BulkDocumentItemOut] = []
    for document_id in payload.document_ids:
        try:
            async with db.begin_nested():
                document = await get_document(db, document_id, lock=True)
                if payload.action == "HIDE":
                    if document.status not in {DocumentStatus.ACTIVE, DocumentStatus.OUTDATED}:
                        items.append(
                            BulkDocumentItemOut(
                                document_id=document_id,
                                outcome="SKIPPED",
                                reason="Несовместимый статус",
                            )
                        )
                        continue
                    document.status = DocumentStatus.HIDDEN
                    document.hidden_reason = (payload.reason or "").strip()
                elif payload.action == "RESTORE":
                    if document.status != DocumentStatus.HIDDEN:
                        items.append(
                            BulkDocumentItemOut(
                                document_id=document_id,
                                outcome="SKIPPED",
                                reason="Документ не скрыт",
                            )
                        )
                        continue
                    document.status = DocumentStatus.ACTIVE
                    document.hidden_reason = None
                else:
                    job = await create_reindex_job(
                        db,
                        request,
                        actor,
                        document,
                        batch_id=str(batch_id),
                        audit=False,
                    )
                    items.append(
                        BulkDocumentItemOut(
                            document_id=document_id, outcome="SUCCESS", job_id=job.id
                        )
                    )
                    continue
                document.version += 1
                document.last_edited_by = actor.id
                document.last_edited_at = utc_now()
                items.append(BulkDocumentItemOut(document_id=document_id, outcome="SUCCESS"))
        except ApiException as exc:
            items.append(
                BulkDocumentItemOut(document_id=document_id, outcome="FAILED", reason=exc.message)
            )
    action_map = {
        "HIDE": AuditAction.BULK_HIDE_DOCUMENTS,
        "RESTORE": AuditAction.BULK_RESTORE_DOCUMENTS,
        "REINDEX": AuditAction.BULK_REINDEX_DOCUMENTS,
    }
    success_count = sum(item.outcome == "SUCCESS" for item in items)
    skipped_count = sum(item.outcome == "SKIPPED" for item in items)
    failed_count = sum(item.outcome == "FAILED" for item in items)
    await add_audit_event(
        db,
        request,
        actor=actor,
        action=action_map[payload.action],
        entity_type=AuditEntityType.DOCUMENT_BATCH,
        entity_id=str(batch_id),
        entity_label=f"Пакет из {len(payload.document_ids)} документов",
        summary="Выполнена массовая операция с документами",
        after={
            "action": payload.action,
            "successCount": success_count,
            "skippedCount": skipped_count,
            "failedCount": failed_count,
        },
        batch_id=str(batch_id),
    )
    return BulkDocumentResultOut(
        batch_id=batch_id,
        action=payload.action,
        success_count=success_count,
        skipped_count=skipped_count,
        failed_count=failed_count,
        items=items,
    )


async def list_jobs(
    db: AsyncSession,
    *,
    job_id: str,
    type_filter: str,
    status: str,
    stage: str,
    actor: str,
    document_id: str,
    source: str,
    date_from: datetime | None,
    date_to: datetime | None,
    sort: str,
    page: int,
    limit: int,
) -> JobsResponse:
    filters = []
    if job_id:
        filters.append(Job.id == UUID(job_id))
    if type_filter != "ALL":
        filters.append(Job.type == type_filter)
    if status != "ALL":
        filters.append(Job.status == status)
    if stage != "ALL":
        filters.append(Job.stage == stage)
    if actor:
        filters.append(Job.created_by == UUID(actor))
    if document_id:
        filters.append(Job.document_id == UUID(document_id))
    if source:
        filters.append(Job.source_id == UUID(source))
    if date_from is not None:
        filters.append(Job.created_at >= date_from)
    if date_to is not None:
        filters.append(Job.created_at <= date_to)
    total = await db.scalar(select(func.count()).select_from(Job).where(*filters)) or 0
    statement = select(Job).where(*filters).options(selectinload(Job.creator))
    if sort == "created_desc":
        statement = statement.order_by(Job.created_at.desc(), Job.id)
    elif sort == "created_asc":
        statement = statement.order_by(Job.created_at.asc(), Job.id)
    elif sort == "progress_desc":
        statement = statement.order_by(Job.progress.desc(), Job.id)
    else:
        raise ApiException(422, "VALIDATION_ERROR", "Неизвестная сортировка")
    jobs = (await db.scalars(statement.offset((page - 1) * limit).limit(limit))).all()
    return JobsResponse(
        items=[job_to_schema(item) for item in jobs],
        pagination=pagination(page, limit, total),
    )


async def editor_dashboard(db: AsyncSession) -> EditorDashboardOut:
    status_rows = (
        await db.execute(select(Document.status, func.count()).group_by(Document.status))
    ).all()
    status_counts = {status: 0 for status in DocumentStatus}
    for status, count in status_rows:
        status_counts[DocumentStatus(status)] = count
    total = sum(status_counts.values())
    bm25_failed = (
        await db.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.bm25_status == IndexStatus.FAILED)
        )
        or 0
    )
    vector_failed = (
        await db.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.vector_status == IndexStatus.FAILED)
        )
        or 0
    )
    active_jobs = (
        await db.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]))
        )
        or 0
    )
    completed_last_day = (
        await db.scalar(
            select(func.count())
            .select_from(Job)
            .where(
                Job.status == JobStatus.COMPLETED, Job.finished_at >= utc_now() - timedelta(days=1)
            )
        )
        or 0
    )
    attention = (
        (
            await db.scalars(
                document_statement()
                .where(
                    or_(
                        Document.status.in_([DocumentStatus.FAILED, DocumentStatus.PENDING]),
                        Document.bm25_status == IndexStatus.FAILED,
                        Document.vector_status == IndexStatus.FAILED,
                    )
                )
                .order_by(Document.updated_at.desc())
                .limit(5)
            )
        )
        .unique()
        .all()
    )
    recent_documents = (
        (
            await db.scalars(
                document_statement()
                .where(Document.last_edited_at.is_not(None))
                .order_by(Document.last_edited_at.desc())
                .limit(5)
            )
        )
        .unique()
        .all()
    )
    recent_jobs = (
        await db.scalars(
            select(Job).options(selectinload(Job.creator)).order_by(Job.created_at.desc()).limit(5)
        )
    ).all()
    failed_jobs = (
        await db.scalars(
            select(Job)
            .where(Job.status == JobStatus.FAILED)
            .options(selectinload(Job.creator))
            .order_by(Job.created_at.desc())
            .limit(5)
        )
    ).all()
    return EditorDashboardOut(
        total_documents=total,
        status_counts=status_counts,
        bm25_failed=bm25_failed,
        vector_failed=vector_failed,
        active_jobs=active_jobs,
        completed_jobs_last_day=completed_last_day,
        attention_documents=[await managed_document_to_schema(db, item) for item in attention],
        recently_edited_documents=[
            await managed_document_to_schema(db, item) for item in recent_documents
        ],
        recent_jobs=[job_to_schema(item) for item in recent_jobs],
        recent_failed_jobs=[job_to_schema(item) for item in failed_jobs],
    )
