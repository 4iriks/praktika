from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.enums import (
    DeduplicationStatus,
    IndexStatus,
    IngestionResultStatus,
    ProcessingStatus,
)
from app.db.models.content import (
    Answer,
    Document,
    DocumentChunk,
    DocumentRevision,
    DocumentTag,
)
from app.db.models.operations import Source
from app.db.session import SessionFactory
from app.integrations.stackexchange.schemas import StackExchangeAnswer, StackExchangeQuestion
from app.services.document_ingestion import IngestionResult, ingest_question_thread

pytestmark = pytest.mark.integration
NOW = datetime(2026, 7, 16, 18, tzinfo=UTC)


def ingestion_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "APP_ENV": "test",
        "CHUNK_TARGET_TOKENS": 50,
        "CHUNK_MAX_TOKENS": 100,
        "CHUNK_OVERLAP_TOKENS": 5,
        "CHUNK_MIN_TOKENS": 3,
        "MIN_QUESTION_TEXT_LENGTH": 10,
        "DOCUMENT_REVISION_LIMIT": 3,
    }
    values.update(overrides)
    return Settings(**values)


def question(
    external_id: int = 900_001,
    *,
    body: str = "<p>Как обработать коллекцию Python безопасно и детерминированно?</p>",
    score: int = 7,
    views: int = 100,
    tags: list[str] | None = None,
    accepted_answer_id: int | None = 910_001,
) -> StackExchangeQuestion:
    return StackExchangeQuestion(
        question_id=external_id,
        title="Обработка &lt;коллекции&gt; в Python",
        body=body,
        tags=tags or ["python", "collections"],
        link=f"https://ru.stackoverflow.com/questions/{external_id}/slug?utm_source=test#answer",
        owner={
            "user_id": 77,
            "display_name": "Автор вопроса",
            "link": "https://ru.stackoverflow.com/users/77/author",
        },
        creation_date=1_700_000_000,
        last_activity_date=1_700_001_000,
        last_edit_date=1_700_000_900,
        score=score,
        view_count=views,
        answer_count=3,
        accepted_answer_id=accepted_answer_id,
        is_answered=True,
        content_license="CC BY-SA 4.0",
    )


def answers(
    *,
    accepted_id: int = 910_001,
    include_second: bool = True,
    changed: bool = False,
) -> list[StackExchangeAnswer]:
    values = [
        StackExchangeAnswer(
            answer_id=accepted_id,
            question_id=900_001,
            body=(
                "<p>Используйте словарь с сохранением порядка.</p>"
                "<pre><code class='language-python'>result = list(dict.fromkeys(values))\n"
                "print(result)</code></pre>"
                + ("<p>Добавлена проверка входа.</p>" if changed else "")
            ),
            owner={
                "user_id": 88,
                "display_name": "Эксперт",
                "link": "https://ru.stackoverflow.com/users/88/expert",
            },
            creation_date=1_700_000_100,
            last_activity_date=1_700_000_500,
            score=15,
            is_accepted=True,
            content_license="CC BY-SA 4.0",
        )
    ]
    if include_second:
        values.append(
            StackExchangeAnswer(
                answer_id=910_002,
                question_id=900_001,
                body="<p>Альтернатива: пройти список и хранить множество увиденных значений.</p>",
                creation_date=1_700_000_200,
                last_activity_date=1_700_000_300,
                score=4,
                is_accepted=False,
            )
        )
    return values


async def source_id(db: AsyncSession) -> UUID:
    value = await db.scalar(select(Source.id).order_by(Source.id))
    assert value is not None
    await db.rollback()
    return value


async def ingest(
    source_identifier: UUID,
    item: StackExchangeQuestion,
    item_answers: list[StackExchangeAnswer],
    *,
    settings: Settings | None = None,
) -> IngestionResult:
    async with SessionFactory() as session, session.begin():
        source = await session.get(Source, source_identifier)
        assert source is not None
        return await ingest_question_thread(
            session,
            source,
            item,
            item_answers,
            settings=settings or ingestion_settings(),
            now=NOW,
        )


async def load_document(source_identifier: UUID, external_id: int) -> Document:
    async with SessionFactory() as session:
        value = await session.scalar(
            select(Document)
            .where(
                Document.source_id == source_identifier,
                Document.external_id == str(external_id),
            )
            .options(
                selectinload(Document.answers),
                selectinload(Document.chunks),
                selectinload(Document.revisions),
                selectinload(Document.tag_links).selectinload(DocumentTag.tag),
            )
        )
        assert value is not None
        return value


async def test_ingestion_persists_question_answers_tags_revisions_and_chunks(
    db: AsyncSession,
) -> None:
    identifier = await source_id(db)
    result = await ingest(identifier, question(), answers())
    document = await load_document(identifier, 900_001)

    assert result.status == IngestionResultStatus.INSERTED
    assert document.processing_status == ProcessingStatus.CHUNKED
    assert document.deduplication_status == DeduplicationStatus.UNIQUE
    assert document.bm25_status == document.vector_status == IndexStatus.NOT_INDEXED
    assert document.source_url == "https://ru.stackoverflow.com/questions/900001"
    assert document.canonical_text and "## Принятый ответ" in document.canonical_text
    assert document.metadata_hash and len(document.metadata_hash) == 64
    assert document.version == 1
    assert document.selected_answers_count == 2
    assert len(document.answers) == 2
    assert all(answer.body_hash and answer.sanitized_html for answer in document.answers)
    assert all("<script" not in (answer.sanitized_html or "") for answer in document.answers)
    assert {link.tag.normalized_name for link in document.tag_links} == {
        "python",
        "collections",
    }
    assert len(document.revisions) == 1
    assert document.chunks_count == len(document.chunks) > 0
    assert any(chunk.has_code for chunk in document.chunks)
    assert all(chunk.document_version == 1 for chunk in document.chunks)


async def test_unchanged_and_metadata_only_update_keep_version_chunks_and_revision(
    db: AsyncSession,
) -> None:
    identifier = await source_id(db)
    await ingest(identifier, question(), answers())
    first = await load_document(identifier, 900_001)
    chunk_keys = {chunk.chunk_key for chunk in first.chunks}

    result = await ingest(
        identifier,
        question(score=999, views=5000, tags=["collections", "python"]),
        answers(),
    )
    second = await load_document(identifier, 900_001)
    assert result.status == IngestionResultStatus.UNCHANGED
    assert second.version == 1
    assert len(second.revisions) == 1
    assert {chunk.chunk_key for chunk in second.chunks} == chunk_keys
    assert second.score == 999 and second.views_count == 5000


async def test_content_change_creates_revision_new_version_and_outdated_indexes(
    db: AsyncSession,
) -> None:
    identifier = await source_id(db)
    await ingest(identifier, question(), answers())
    async with SessionFactory() as session, session.begin():
        document = await session.scalar(
            select(Document).where(
                Document.source_id == identifier,
                Document.external_id == "900001",
            )
        )
        assert document is not None
        document.bm25_status = IndexStatus.READY
        document.vector_status = IndexStatus.READY

    result = await ingest(identifier, question(), answers(changed=True))
    changed = await load_document(identifier, 900_001)
    assert result.status == IngestionResultStatus.UPDATED
    assert changed.version == 2
    assert [revision.version for revision in changed.revisions] == [1, 2]
    assert all(chunk.document_version == 2 for chunk in changed.chunks)
    assert changed.bm25_status == changed.vector_status == IndexStatus.OUTDATED


async def test_external_identity_updates_and_exact_duplicate_is_retained(
    db: AsyncSession,
) -> None:
    identifier = await source_id(db)
    await ingest(identifier, question(), answers())
    repeated = await ingest(identifier, question(), answers())
    assert repeated.status == IngestionResultStatus.UNCHANGED

    duplicate_question = question(external_id=900_002, accepted_answer_id=920_001)
    duplicate_answers = [
        item.model_copy(
            update={
                "answer_id": 920_001 + index,
                "question_id": 900_002,
            }
        )
        for index, item in enumerate(answers(accepted_id=920_001))
    ]
    duplicate = await ingest(identifier, duplicate_question, duplicate_answers)
    duplicate_document = await load_document(identifier, 900_002)
    assert duplicate.status == IngestionResultStatus.DUPLICATE
    assert duplicate_document.deduplication_status == DeduplicationStatus.EXACT_DUPLICATE
    assert duplicate_document.duplicate_of_document_id is not None

    async with SessionFactory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.external_id.in_(["900001", "900002"]))
        )
    assert count == 2


async def test_answer_reconciliation_marks_missing_without_deleting(db: AsyncSession) -> None:
    identifier = await source_id(db)
    await ingest(identifier, question(), answers())
    await ingest(identifier, question(), answers(include_second=False))
    document = await load_document(identifier, 900_001)
    by_external = {answer.external_id: answer for answer in document.answers}
    assert len(by_external) == 2
    assert by_external["910002"].source_missing is True
    assert by_external["910002"].selected_for_corpus is False
    assert by_external["910001"].source_missing is False


async def test_revision_retention_is_bounded(db: AsyncSession) -> None:
    identifier = await source_id(db)
    settings = ingestion_settings(DOCUMENT_REVISION_LIMIT=2)
    for index in range(4):
        await ingest(
            identifier,
            question(body=f"<p>Версия вопроса номер {index} с достаточной длиной текста.</p>"),
            answers(changed=bool(index % 2)),
            settings=settings,
        )
    document = await load_document(identifier, 900_001)
    assert document.version == 4
    assert [revision.version for revision in document.revisions] == [3, 4]
    async with SessionFactory() as session:
        chunks = await session.scalar(
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.document_id == document.id)
        )
        answers_count = await session.scalar(
            select(func.count()).select_from(Answer).where(Answer.document_id == document.id)
        )
        revisions = await session.scalar(
            select(func.count())
            .select_from(DocumentRevision)
            .where(DocumentRevision.document_id == document.id)
        )
    assert chunks == document.chunks_count
    assert answers_count == 2
    assert revisions == 2
