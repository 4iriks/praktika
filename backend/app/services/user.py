from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import Request
from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiException
from app.core.enums import AuditAction, AuditEntityType, DocumentStatus, SearchView
from app.db.models.content import Document, DocumentTag, Tag
from app.db.models.identity import Feedback, SavedDocument, SearchHistory, User
from app.db.repositories.users import get_user_by_email, normalize_email
from app.schemas.auth import UpdateProfileRequest, UserOut, UserStatsOut
from app.schemas.base import pagination
from app.schemas.content import (
    FeedbackOut,
    FeedbackRequest,
    HistoryResponse,
    SavedDocumentOut,
    SavedDocumentsResponse,
    SearchHistoryOut,
    TagOut,
)
from app.services.audit import add_audit_event
from app.services.content import selected_tags
from app.services.serializers import user_to_schema


async def update_profile(
    db: AsyncSession, request: Request, user: User, payload: UpdateProfileRequest
) -> UserOut:
    before = {"displayName": user.name, "email": user.email}
    if payload.email is not None and normalize_email(str(payload.email)) != user.normalized_email:
        existing = await get_user_by_email(db, str(payload.email))
        if existing is not None:
            raise ApiException(409, "CONFLICT", "Этот email уже используется")
        user.email = str(payload.email).strip()
        user.normalized_email = normalize_email(str(payload.email))
    if payload.display_name is not None:
        user.name = payload.display_name
    if payload.preferences is not None:
        preferences = payload.preferences
        user.preferences.default_search_mode = preferences.default_search_mode
        user.preferences.default_search_view = preferences.default_search_view
        user.preferences.default_page_size = preferences.default_page_size
        user.preferences.auto_expand_scores = preferences.auto_open_scores
        user.preferences.confirm_external_links = preferences.confirm_external_navigation
    await add_audit_event(
        db,
        request,
        actor=user,
        action=AuditAction.UPDATE_PROFILE,
        entity_type=AuditEntityType.USER,
        entity_id=str(user.id),
        entity_label=user.email,
        summary="Пользователь обновил профиль",
        before=before,
        after={"displayName": user.name, "email": user.email},
    )
    await db.flush()
    return user_to_schema(user)


async def user_stats(db: AsyncSession, user: User) -> UserStatsOut:
    document_searches = await db.scalar(
        select(func.count())
        .select_from(SearchHistory)
        .where(SearchHistory.user_id == user.id, SearchHistory.view == SearchView.DOCUMENTS)
    )
    rag_searches = await db.scalar(
        select(func.count())
        .select_from(SearchHistory)
        .where(SearchHistory.user_id == user.id, SearchHistory.view == SearchView.ANSWER)
    )
    saved = await db.scalar(
        select(func.count()).select_from(SavedDocument).where(SavedDocument.user_id == user.id)
    )
    rated = await db.scalar(
        select(func.count()).select_from(Feedback).where(Feedback.user_id == user.id)
    )
    return UserStatsOut(
        document_searches=document_searches or 0,
        rag_searches=rag_searches or 0,
        saved_documents=saved or 0,
        rated_answers=rated or 0,
    )


def history_schema(item: SearchHistory) -> SearchHistoryOut:
    return SearchHistoryOut(
        id=item.id,
        user_id=item.user_id,
        query=item.query,
        view=item.view,
        mode=item.mode,
        filters=item.filters,
        sort=item.sort,
        page_size=item.page_size,
        result_count=item.result_count,
        took_ms=item.took_ms,
        created_at=item.created_at,
        answer_preview=item.answer_preview,
        insufficient_context=item.insufficient_context,
    )


async def get_history(
    db: AsyncSession,
    user: User,
    *,
    search: str,
    view: str,
    mode: str,
    date_sort: str,
    date_from: datetime | None,
    date_to: datetime | None,
    page: int,
    page_size: int,
) -> HistoryResponse:
    filters = [SearchHistory.user_id == user.id]
    if search:
        filters.append(SearchHistory.query.ilike(f"%{search}%"))
    if view != "all":
        filters.append(SearchHistory.view == view)
    if mode != "all":
        filters.append(SearchHistory.mode == mode)
    if date_from:
        filters.append(SearchHistory.created_at >= date_from)
    if date_to:
        filters.append(SearchHistory.created_at <= date_to)
    total = await db.scalar(select(func.count()).select_from(SearchHistory).where(*filters)) or 0
    order = (
        SearchHistory.created_at.asc() if date_sort == "oldest" else SearchHistory.created_at.desc()
    )
    items = (
        await db.scalars(
            select(SearchHistory)
            .where(*filters)
            .order_by(order, SearchHistory.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return HistoryResponse(
        items=[history_schema(item) for item in items],
        pagination=pagination(page, page_size, total),
    )


async def delete_history_item(db: AsyncSession, user: User, history_id: UUID) -> None:
    deleted_id = await db.scalar(
        delete(SearchHistory)
        .where(
            SearchHistory.id == history_id,
            SearchHistory.user_id == user.id,
        )
        .returning(SearchHistory.id)
    )
    if deleted_id is None:
        raise ApiException(404, "NOT_FOUND", "Запись истории не найдена")


async def clear_history(db: AsyncSession, user: User) -> None:
    await db.execute(delete(SearchHistory).where(SearchHistory.user_id == user.id))


def saved_schema(document: Document, saved_at: datetime) -> SavedDocumentOut:
    tags = selected_tags(document)
    return SavedDocumentOut(
        document_id=str(document.id),
        title=document.normalized_title,
        snippet=document.question_text[:260],
        tags=[TagOut(name=tag.display_name, slug=tag.normalized_name) for tag in tags],
        source_url=document.source_url,
        published_at=document.published_at,
        question_score=document.score,
        answers_count=document.answers_count,
        accepted_answer=document.accepted_answer_external_id is not None,
        has_code=document.has_code,
        saved_at=saved_at,
    )


async def get_saved_documents(
    db: AsyncSession,
    user: User,
    *,
    search: str,
    tags: list[str],
    sort: str,
    page: int,
    page_size: int,
) -> SavedDocumentsResponse:
    filters = [
        SavedDocument.user_id == user.id,
        Document.status.in_([DocumentStatus.ACTIVE, DocumentStatus.OUTDATED]),
    ]
    if search:
        filters.append(
            or_(
                Document.normalized_title.ilike(f"%{search}%"),
                Document.question_text.ilike(f"%{search}%"),
            )
        )
    if tags:
        filters.append(
            Document.id.in_(
                select(DocumentTag.document_id)
                .join(Tag, Tag.id == DocumentTag.tag_id)
                .where(Tag.normalized_name.in_(tags))
            )
        )
    base = (
        select(SavedDocument, Document)
        .join(Document, Document.id == SavedDocument.document_id)
        .where(*filters)
    )
    total = await db.scalar(select(func.count()).select_from(base.subquery())) or 0
    if sort == "score":
        base = base.order_by(Document.score.desc(), Document.id)
    elif sort == "publishedAt":
        base = base.order_by(Document.published_at.desc(), Document.id)
    else:
        base = base.order_by(SavedDocument.saved_at.desc(), Document.id)
    rows = (await db.execute(base.offset((page - 1) * page_size).limit(page_size))).all()
    available = (
        (
            await db.execute(
                select(Tag)
                .join(DocumentTag, DocumentTag.tag_id == Tag.id)
                .join(SavedDocument, SavedDocument.document_id == DocumentTag.document_id)
                .where(SavedDocument.user_id == user.id)
                .distinct()
                .order_by(Tag.normalized_name)
            )
        )
        .scalars()
        .all()
    )
    return SavedDocumentsResponse(
        items=[saved_schema(document, saved.saved_at) for saved, document in rows],
        available_tags=[
            TagOut(name=tag.display_name, slug=tag.normalized_name) for tag in available
        ],
        pagination=pagination(page, page_size, total),
    )


async def save_document(db: AsyncSession, user: User, document_id: UUID) -> SavedDocumentOut:
    document = await db.get(Document, document_id)
    if document is None:
        raise ApiException(404, "NOT_FOUND", "Документ не найден")
    if document.status not in {DocumentStatus.ACTIVE, DocumentStatus.OUTDATED}:
        raise ApiException(404, "NOT_FOUND", "Документ временно недоступен")
    statement = (
        insert(SavedDocument)
        .values(user_id=user.id, document_id=document.id)
        .on_conflict_do_nothing(index_elements=["user_id", "document_id"])
        .returning(SavedDocument.saved_at)
    )
    saved_at = await db.scalar(statement)
    if saved_at is None:
        saved_at = await db.scalar(
            select(SavedDocument.saved_at).where(
                SavedDocument.user_id == user.id, SavedDocument.document_id == document.id
            )
        )
    if saved_at is None:
        raise ApiException(500, "INTERNAL_ERROR", "Не удалось сохранить документ")
    await db.refresh(document, attribute_names=["tag_links"])
    return saved_schema(document, saved_at)


async def unsave_document(db: AsyncSession, user: User, document_id: UUID) -> None:
    await db.execute(
        delete(SavedDocument).where(
            SavedDocument.user_id == user.id, SavedDocument.document_id == document_id
        )
    )


def feedback_schema(item: Feedback) -> FeedbackOut:
    return FeedbackOut.model_validate(item)


async def upsert_feedback(db: AsyncSession, user: User, payload: FeedbackRequest) -> FeedbackOut:
    values = payload.model_dump()
    statement = (
        insert(Feedback)
        .values(user_id=user.id, **values)
        .on_conflict_do_update(
            index_elements=["user_id", "response_id"],
            set_={
                "value": values["value"],
                "reason": values["reason"],
                "question": values["question"],
                "comment": values["comment"],
                "updated_at": func.now(),
            },
        )
        .returning(Feedback)
    )
    item = (await db.scalars(statement)).one()
    return feedback_schema(item)


async def get_feedback(db: AsyncSession, user: User, response_id: str) -> FeedbackOut | None:
    item = await db.scalar(
        select(Feedback).where(Feedback.user_id == user.id, Feedback.response_id == response_id)
    )
    return feedback_schema(item) if item else None


async def delete_feedback(db: AsyncSession, user: User, feedback_id: UUID) -> None:
    deleted_id = await db.scalar(
        delete(Feedback)
        .where(Feedback.id == feedback_id, Feedback.user_id == user.id)
        .returning(Feedback.id)
    )
    if deleted_id is None:
        raise ApiException(404, "NOT_FOUND", "Оценка не найдена")
