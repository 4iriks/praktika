from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.errors import ApiException
from app.core.enums import DocumentStatus, IndexStatus
from app.db.models.content import Document, DocumentTag, Tag
from app.db.models.identity import SavedDocument, User
from app.schemas.content import (
    AnswerOut,
    DocumentOut,
    QuestionOut,
    ScoreBreakdownOut,
    TagOut,
)
from app.services.serializers import code_blocks


def document_statement() -> Select[tuple[Document]]:
    return select(Document).options(
        selectinload(Document.answers),
        selectinload(Document.tag_links).selectinload(DocumentTag.tag),
        selectinload(Document.source),
        selectinload(Document.editor),
    )


async def get_document(db: AsyncSession, document_id: UUID, *, lock: bool = False) -> Document:
    statement = document_statement().where(Document.id == document_id)
    if lock:
        statement = statement.with_for_update()
    result = await db.execute(statement)
    document = result.scalar_one_or_none()
    if document is None:
        raise ApiException(404, "NOT_FOUND", "Документ не найден")
    return document


def selected_tags(document: Document) -> list[Tag]:
    managed = [link.tag for link in document.tag_links if link.is_managed]
    selected = managed or [link.tag for link in document.tag_links if not link.is_managed]
    return sorted(selected, key=lambda tag: tag.normalized_name)


async def is_saved(db: AsyncSession, user: User | None, document_id: UUID) -> bool:
    if user is None:
        return False
    return bool(
        await db.scalar(
            select(
                exists().where(
                    SavedDocument.user_id == user.id,
                    SavedDocument.document_id == document_id,
                )
            )
        )
    )


async def document_to_schema(
    db: AsyncSession, document: Document, user: User | None = None
) -> DocumentOut:
    indexed_at = document.last_indexed_at or document.last_synced_at or datetime.now(UTC)
    return DocumentOut(
        id=str(document.id),
        title=document.normalized_title,
        source_url=document.source_url,
        published_at=document.published_at,
        author=document.author_name,
        views=document.views_count,
        score=document.score,
        tags=[
            TagOut(name=tag.display_name, slug=tag.normalized_name)
            for tag in selected_tags(document)
        ],
        question=QuestionOut(
            body=document.question_text,
            code_blocks=code_blocks(document.question_text),
        ),
        answers=[
            AnswerOut(
                id=str(answer.id),
                author=answer.author_name,
                body=answer.body_text,
                code_blocks=code_blocks(answer.body_text),
                score=answer.score,
                accepted=answer.is_accepted,
                created_at=answer.published_at,
            )
            for answer in sorted(
                document.answers,
                key=lambda item: (not item.is_accepted, -item.score),
            )
        ],
        chunk_count=document.chunks_count,
        indexed_at=indexed_at,
        bm25_status=IndexStatus(document.bm25_status),
        vector_status=IndexStatus(document.vector_status),
        content_hash=document.content_hash,
        saved=await is_saved(db, user, document.id),
        scores=ScoreBreakdownOut(),
    )


async def get_public_document(
    db: AsyncSession, document_id: UUID, user: User | None
) -> DocumentOut:
    document = await get_document(db, document_id)
    if document.status not in {DocumentStatus.ACTIVE, DocumentStatus.OUTDATED}:
        raise ApiException(
            404,
            "NOT_FOUND",
            "Документ временно недоступен",
            {"reason": "DOCUMENT_UNAVAILABLE"},
        )
    return await document_to_schema(db, document, user)
