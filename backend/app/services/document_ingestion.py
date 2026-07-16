from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.enums import (
    DeduplicationStatus,
    DocumentStatus,
    IndexStatus,
    IngestionResultStatus,
    ProcessingStatus,
)
from app.db.base import utc_now
from app.db.models.content import (
    Answer,
    Document,
    DocumentChunk,
    DocumentRevision,
    DocumentTag,
    Tag,
)
from app.db.models.operations import Source
from app.integrations.stackexchange.schemas import StackExchangeAnswer, StackExchangeQuestion
from app.processing.canonical import CanonicalDocument, build_canonical_document
from app.processing.chunking import ChunkingSettings, DocumentChunker, stable_chunk_key
from app.processing.html import CleanedContent, HtmlContentError, clean_html, clean_title
from app.processing.normalization import canonical_stackoverflow_question_url
from app.processing.selection import (
    AnswerSelection,
    ProcessedAnswer,
    select_corpus_answers,
)
from app.services.index_jobs import enqueue_document_reindex


class IngestionSkip(ValueError):
    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


@dataclass(frozen=True, slots=True)
class PreparationWarning:
    code: str
    external_id: str | None
    message: str


@dataclass(frozen=True, slots=True)
class PreparedQuestionThread:
    question: StackExchangeQuestion
    title: str
    question_content: CleanedContent
    answers: tuple[ProcessedAnswer, ...]
    selection: AnswerSelection
    source_url: str
    warnings: tuple[PreparationWarning, ...]


@dataclass(frozen=True, slots=True)
class IngestionResult:
    status: IngestionResultStatus
    document_id: UUID
    version: int
    chunks_created: int
    warnings: tuple[PreparationWarning, ...]


def prepare_question_thread(
    question: StackExchangeQuestion,
    answers: list[StackExchangeAnswer],
    *,
    settings: Settings,
    max_additional_answers: int,
) -> PreparedQuestionThread:
    if len(answers) > settings.max_answer_count_per_question:
        raise IngestionSkip(
            "TOO_MANY_ANSWERS",
            "Количество ответов вопроса превысило безопасный предел",
        )
    title = clean_title(question.title)
    if not title:
        raise IngestionSkip("EMPTY_TITLE", "Заголовок вопроса пуст после очистки")
    try:
        question_content = clean_html(
            question.body,
            maximum_input_bytes=settings.max_html_body_bytes,
            maximum_output_characters=settings.max_document_text_length,
        )
    except HtmlContentError as exc:
        raise IngestionSkip(exc.code, exc.safe_message) from exc
    if len(question_content.text) < settings.min_question_text_length:
        raise IngestionSkip(
            "QUESTION_TOO_SHORT",
            "Текст вопроса слишком короткий после очистки",
        )

    processed_answers: list[ProcessedAnswer] = []
    warnings: list[PreparationWarning] = []
    for answer in answers:
        if answer.question_id != question.question_id:
            warnings.append(
                PreparationWarning(
                    "ANSWER_QUESTION_MISMATCH",
                    str(answer.answer_id),
                    "Ответ относится к другому вопросу и исключён из обработки",
                )
            )
            continue
        try:
            content = clean_html(
                answer.body,
                maximum_input_bytes=settings.max_html_body_bytes,
                maximum_output_characters=settings.max_document_text_length,
            )
        except HtmlContentError as exc:
            warnings.append(PreparationWarning(exc.code, str(answer.answer_id), exc.safe_message))
            continue
        if len(content.text) < settings.min_answer_text_length:
            warnings.append(
                PreparationWarning(
                    "ANSWER_TOO_SHORT",
                    str(answer.answer_id),
                    "Ответ пуст после очистки и исключён из corpus",
                )
            )
        processed_answers.append(ProcessedAnswer(answer, content))
    selection = select_corpus_answers(
        question,
        processed_answers,
        max_additional_answers=max_additional_answers,
    )
    if selection.missing_accepted:
        warnings.append(
            PreparationWarning(
                "ACCEPTED_ANSWER_MISSING",
                str(question.accepted_answer_id),
                "Заявленный принятый ответ не получен из Stack Exchange API",
            )
        )
    try:
        source_url = canonical_stackoverflow_question_url(question.question_id, question.link)
    except ValueError as exc:
        raise IngestionSkip("INVALID_SOURCE_URL", str(exc)) from exc
    return PreparedQuestionThread(
        question=question,
        title=title,
        question_content=question_content,
        answers=tuple(processed_answers),
        selection=selection,
        source_url=source_url,
        warnings=tuple(warnings),
    )


async def ingest_question_thread(
    db: AsyncSession,
    source: Source,
    question: StackExchangeQuestion,
    answers: list[StackExchangeAnswer],
    *,
    settings: Settings,
    now: datetime | None = None,
) -> IngestionResult:
    prepared = prepare_question_thread(
        question,
        answers,
        settings=settings,
        max_additional_answers=source.max_additional_answers,
    )
    moment = now or utc_now()
    document = await db.scalar(
        select(Document)
        .where(
            Document.source_id == source.id,
            Document.external_id == str(question.question_id),
        )
        .options(
            selectinload(Document.answers),
            selectinload(Document.revisions),
            selectinload(Document.chunks),
        )
        .with_for_update()
    )
    is_new = document is None
    if document is None:
        document = _new_document(source, prepared, moment)
        db.add(document)
        await db.flush()

    effective_title = (
        document.normalized_title
        if document.last_edited_at is not None and document.normalized_title.strip()
        else prepared.title
    )
    canonical = build_canonical_document(
        question,
        title=effective_title,
        question_content=prepared.question_content,
        selection=prepared.selection,
    )
    previous_content_hash = None if is_new else document.content_hash
    content_changed = previous_content_hash != canonical.content_hash
    if content_changed and not is_new:
        document.version += 1

    answer_records = await _upsert_answers(db, document, prepared, moment)
    await _replace_source_tags(db, document.id, canonical.tags)
    _apply_document_fields(document, prepared, canonical, moment, preserve_editor=not is_new)
    await _apply_exact_deduplication(db, document, canonical.content_hash)

    chunks_created = 0
    if content_changed:
        await _create_revision(db, document, prepared, canonical, settings, moment)
        chunks_created = await _replace_chunks(
            db,
            document,
            canonical,
            answer_records,
            settings,
        )
        document.processing_status = ProcessingStatus.CHUNKED
        document.processing_error = None
        document.chunks_count = chunks_created
        if is_new:
            document.bm25_status = IndexStatus.NOT_INDEXED
            document.vector_status = IndexStatus.NOT_INDEXED
        else:
            document.bm25_status = _outdated_index_status(document.bm25_status)
            document.vector_status = _outdated_index_status(document.vector_status)
    elif document.processing_status != ProcessingStatus.CHUNKED:
        document.processing_status = ProcessingStatus.CHUNKED
        document.processing_error = None
    if content_changed and document.deduplication_status != DeduplicationStatus.EXACT_DUPLICATE:
        await enqueue_document_reindex(db, document, settings=settings)
    await db.flush()

    if document.deduplication_status == DeduplicationStatus.EXACT_DUPLICATE:
        status = IngestionResultStatus.DUPLICATE
    elif is_new:
        status = IngestionResultStatus.INSERTED
    elif content_changed:
        status = IngestionResultStatus.UPDATED
    else:
        status = IngestionResultStatus.UNCHANGED
    return IngestionResult(
        status=status,
        document_id=document.id,
        version=document.version,
        chunks_created=chunks_created,
        warnings=prepared.warnings,
    )


def _new_document(
    source: Source,
    prepared: PreparedQuestionThread,
    moment: datetime,
) -> Document:
    question = prepared.question
    return Document(
        source_id=source.id,
        external_id=str(question.question_id),
        source_url=prepared.source_url,
        original_title=prepared.title,
        normalized_title=prepared.title,
        question_text=prepared.question_content.text,
        question_html=prepared.question_content.sanitized_html,
        author_name=_owner_name(question.owner.display_name if question.owner else ""),
        author_profile_url=question.owner.link if question.owner else None,
        content_license=question.content_license,
        published_at=_timestamp(question.creation_date),
        source_updated_at=_timestamp(question.last_edit_date or question.last_activity_date),
        score=question.score,
        views_count=question.view_count,
        answers_count=question.answer_count,
        accepted_answer_external_id=(
            str(question.accepted_answer_id) if question.accepted_answer_id else None
        ),
        has_code=prepared.question_content.has_code,
        status=DocumentStatus.ACTIVE,
        bm25_status=IndexStatus.NOT_INDEXED,
        vector_status=IndexStatus.NOT_INDEXED,
        chunks_count=0,
        content_hash="",
        metadata_hash=None,
        canonical_text=None,
        processing_status=ProcessingStatus.CLEANING,
        deduplication_status=DeduplicationStatus.UNIQUE,
        last_seen_at=moment,
        selected_answers_count=0,
        last_synced_at=moment,
        version=1,
        answers=[],
        revisions=[],
        chunks=[],
    )


def _apply_document_fields(
    document: Document,
    prepared: PreparedQuestionThread,
    canonical: CanonicalDocument,
    moment: datetime,
    *,
    preserve_editor: bool,
) -> None:
    question = prepared.question
    document.source_url = prepared.source_url
    document.original_title = prepared.title
    if not preserve_editor or document.last_edited_at is None:
        document.normalized_title = prepared.title
    document.question_text = prepared.question_content.text
    document.question_html = prepared.question_content.sanitized_html
    document.author_name = _owner_name(question.owner.display_name if question.owner else "")
    document.author_profile_url = question.owner.link if question.owner else None
    document.content_license = question.content_license
    document.published_at = _timestamp(question.creation_date)
    document.source_updated_at = _timestamp(question.last_edit_date or question.last_activity_date)
    document.score = question.score
    document.views_count = question.view_count
    document.answers_count = question.answer_count
    document.accepted_answer_external_id = (
        str(question.accepted_answer_id) if question.accepted_answer_id else None
    )
    document.has_code = prepared.question_content.has_code or any(
        item.answer.content.has_code for item in prepared.selection.selected
    )
    document.content_hash = canonical.content_hash
    document.metadata_hash = canonical.metadata_hash
    document.canonical_text = canonical.text
    document.last_seen_at = moment
    document.last_synced_at = moment
    document.selected_answers_count = len(prepared.selection.selected)
    document.processing_error = None


async def _upsert_answers(
    db: AsyncSession,
    document: Document,
    prepared: PreparedQuestionThread,
    moment: datetime,
) -> dict[str, Answer]:
    existing = {answer.external_id: answer for answer in document.answers}
    for answer in existing.values():
        answer.selected_for_corpus = False
        answer.selection_rank = None
        answer.source_missing = True
    selected = {str(item.answer.source.answer_id): item for item in prepared.selection.selected}
    for processed in prepared.answers:
        dto = processed.source
        external_id = str(dto.answer_id)
        record = existing.get(external_id)
        if record is None:
            record = Answer(
                document_id=document.id,
                external_id=external_id,
                author_name=_owner_name(dto.owner.display_name if dto.owner else ""),
                body_text=processed.content.text,
                body_html=dto.body,
                sanitized_html=processed.content.sanitized_html,
                body_hash=_text_hash(processed.content.text),
                score=dto.score,
                is_accepted=False,
                published_at=_timestamp(dto.creation_date),
                source_updated_at=_timestamp(dto.last_edit_date or dto.last_activity_date),
                last_seen_at=moment,
                selected_for_corpus=False,
                source_missing=False,
                content_license=dto.content_license,
                author_profile_url=dto.owner.link if dto.owner else None,
            )
            db.add(record)
            existing[external_id] = record
        chosen = selected.get(external_id)
        record.author_name = _owner_name(dto.owner.display_name if dto.owner else "")
        record.author_profile_url = dto.owner.link if dto.owner else None
        record.body_text = processed.content.text
        record.body_html = dto.body
        record.sanitized_html = processed.content.sanitized_html
        record.body_hash = _text_hash(processed.content.text)
        record.score = dto.score
        record.is_accepted = bool(
            dto.is_accepted or prepared.question.accepted_answer_id == dto.answer_id
        )
        record.published_at = _timestamp(dto.creation_date)
        record.source_updated_at = _timestamp(dto.last_edit_date or dto.last_activity_date)
        record.last_seen_at = moment
        record.selected_for_corpus = chosen is not None
        record.selection_rank = chosen.rank if chosen else None
        record.source_missing = False
        record.content_license = dto.content_license
    await db.flush()
    return existing


async def _replace_source_tags(
    db: AsyncSession,
    document_id: UUID,
    normalized_tags: tuple[str, ...],
) -> None:
    await db.execute(
        delete(DocumentTag).where(
            DocumentTag.document_id == document_id,
            DocumentTag.is_managed.is_(False),
        )
    )
    if not normalized_tags:
        return
    for tag_name in normalized_tags:
        await db.execute(
            insert(Tag)
            .values(normalized_name=tag_name, display_name=tag_name)
            .on_conflict_do_nothing(index_elements=[Tag.normalized_name])
        )
    tags = (await db.scalars(select(Tag).where(Tag.normalized_name.in_(normalized_tags)))).all()
    db.add_all(
        [DocumentTag(document_id=document_id, tag_id=tag.id, is_managed=False) for tag in tags]
    )
    await db.flush()


async def _apply_exact_deduplication(
    db: AsyncSession,
    document: Document,
    content_hash: str,
) -> None:
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(content_hash))))
    duplicate_of = await db.scalar(
        select(Document)
        .where(
            Document.id != document.id,
            Document.content_hash == content_hash,
            Document.duplicate_of_document_id.is_(None),
            Document.deduplication_status != DeduplicationStatus.EXACT_DUPLICATE,
        )
        .order_by(Document.created_at, Document.id)
        .limit(1)
    )
    if duplicate_of is None:
        document.deduplication_status = DeduplicationStatus.UNIQUE
        document.duplicate_of_document_id = None
    else:
        document.deduplication_status = DeduplicationStatus.EXACT_DUPLICATE
        document.duplicate_of_document_id = duplicate_of.id


async def _create_revision(
    db: AsyncSession,
    document: Document,
    prepared: PreparedQuestionThread,
    canonical: CanonicalDocument,
    settings: Settings,
    moment: datetime,
) -> None:
    db.add(
        DocumentRevision(
            document_id=document.id,
            version=document.version,
            content_hash=canonical.content_hash,
            metadata_hash=canonical.metadata_hash,
            source_updated_at=document.source_updated_at,
            snapshot={
                "title": canonical.title,
                "tags": list(canonical.tags),
                "questionText": prepared.question_content.text,
                "selectedAnswers": [
                    {
                        "externalId": str(item.answer.source.answer_id),
                        "textHash": _text_hash(item.answer.content.text),
                        "accepted": item.accepted,
                    }
                    for item in prepared.selection.selected
                ],
                "metadata": {
                    "score": prepared.question.score,
                    "views": prepared.question.view_count,
                    "answerCount": prepared.question.answer_count,
                },
            },
            change_reason="INITIAL_IMPORT" if document.version == 1 else "SOURCE_CONTENT_CHANGED",
            created_at=moment,
        )
    )
    await db.flush()
    obsolete_ids = (
        await db.scalars(
            select(DocumentRevision.id)
            .where(DocumentRevision.document_id == document.id)
            .order_by(DocumentRevision.version.desc())
            .offset(settings.document_revision_limit)
        )
    ).all()
    if obsolete_ids:
        await db.execute(delete(DocumentRevision).where(DocumentRevision.id.in_(obsolete_ids)))


async def _replace_chunks(
    db: AsyncSession,
    document: Document,
    canonical: CanonicalDocument,
    answers: dict[str, Answer],
    settings: Settings,
) -> int:
    await db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
    chunker = DocumentChunker(
        ChunkingSettings(
            target_tokens=settings.chunk_target_tokens,
            max_tokens=settings.chunk_max_tokens,
            overlap_tokens=settings.chunk_overlap_tokens,
            min_tokens=settings.chunk_min_tokens,
        )
    )
    drafts = chunker.chunk(canonical)
    for draft in drafts:
        answer = answers.get(draft.answer_external_id or "")
        db.add(
            DocumentChunk(
                chunk_key=stable_chunk_key(
                    document.id,
                    document.version,
                    draft.ordinal,
                    draft.content_hash,
                ),
                document_id=document.id,
                document_version=document.version,
                ordinal=draft.ordinal,
                section_type=draft.section_type,
                answer_id=answer.id if answer else None,
                text=draft.text,
                contextual_text=draft.contextual_text,
                content_hash=draft.content_hash,
                token_count=draft.token_count,
                character_count=draft.character_count,
                has_code=draft.has_code,
                language=draft.language,
            )
        )
    await db.flush()
    return len(drafts)


def _outdated_index_status(value: str) -> IndexStatus:
    return IndexStatus.NOT_INDEXED if value == IndexStatus.NOT_INDEXED else IndexStatus.OUTDATED


def _timestamp(value: int) -> datetime:
    return datetime.fromtimestamp(value, UTC)


def _owner_name(value: str) -> str:
    return value.strip()[:200] or "Участник Stack Overflow"


def _text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
