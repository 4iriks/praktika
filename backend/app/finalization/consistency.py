from __future__ import annotations

from sqlalchemy import exists, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.base import Executable

from app.core.enums import DocumentStatus, JobStatus
from app.db.models.content import Answer, Document, DocumentChunk, Tag
from app.db.models.operations import Job
from app.finalization.reporting import CheckResult, ReportStatus


async def data_consistency_checks(db: AsyncSession) -> list[CheckResult]:
    duplicate_identity = (
        select(Document.source_id, Document.external_id)
        .group_by(Document.source_id, Document.external_id)
        .having(func.count() > 1)
        .subquery()
    )
    accepted_exists = exists().where(
        Answer.document_id == Document.id,
        Answer.external_id == Document.accepted_answer_external_id,
        Answer.is_accepted.is_(True),
    )
    checks = [
        _zero(
            "document_identity_unique",
            await _count_query(db, select(func.count()).select_from(duplicate_identity)),
        ),
        _zero(
            "active_document_required_fields",
            await _count_query(
                db,
                select(func.count())
                .select_from(Document)
                .where(
                    Document.status == DocumentStatus.ACTIVE,
                    (
                        (func.length(func.btrim(Document.normalized_title)) == 0)
                        | (func.length(func.btrim(Document.question_text)) == 0)
                        | (func.length(func.btrim(Document.source_url)) == 0)
                        | (func.length(func.btrim(Document.content_hash)) == 0)
                    ),
                ),
            ),
        ),
        _zero(
            "accepted_answer_relation",
            await _count_query(
                db,
                select(func.count())
                .select_from(Document)
                .where(Document.accepted_answer_external_id.is_not(None), ~accepted_exists),
            ),
        ),
        _zero(
            "selected_answers_present",
            await _count_query(
                db,
                select(func.count())
                .select_from(Answer)
                .where(
                    Answer.selected_for_corpus.is_(True),
                    (Answer.source_missing.is_(True))
                    | (func.length(func.btrim(Answer.body_text)) == 0),
                ),
            ),
        ),
        _zero(
            "tags_normalized",
            await _count_query(
                db,
                select(func.count())
                .select_from(Tag)
                .where(Tag.normalized_name != func.lower(func.btrim(Tag.normalized_name))),
            ),
        ),
        _zero(
            "chunks_non_empty",
            await _count_query(
                db,
                select(func.count())
                .select_from(DocumentChunk)
                .where(
                    (func.length(func.btrim(DocumentChunk.text)) == 0)
                    | (func.length(func.btrim(DocumentChunk.contextual_text)) == 0)
                ),
            ),
        ),
        _zero(
            "chunk_version_current",
            await _count_query(
                db,
                select(func.count())
                .select_from(DocumentChunk)
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(DocumentChunk.document_version != Document.version),
            ),
        ),
        _zero(
            "jobs_valid_state",
            await _count_query(
                db,
                select(func.count())
                .select_from(Job)
                .where(
                    (Job.progress < 0)
                    | (Job.progress > 100)
                    | (Job.attempt > Job.max_attempts)
                    | ((Job.status == JobStatus.RUNNING) & Job.claimed_by.is_(None))
                ),
            ),
        ),
        _zero(
            "audit_credentials_absent",
            int(
                (
                    await db.scalar(
                        text(
                            "SELECT count(*) FROM audit_events WHERE lower("
                            "coalesce(before::text,'') || coalesce(after::text,'') || "
                            "coalesce(metadata::text,'')) ~ "
                            "'(password_hash|token_hash|csrf_token|session_cookie|api_key)'"
                        )
                    )
                )
                or 0
            ),
        ),
    ]
    document_count = await _count_query(db, select(func.count()).select_from(Document))
    chunk_count = await _count_query(db, select(func.count()).select_from(DocumentChunk))
    checks.append(
        CheckResult(
            code="corpus_has_chunks",
            status=(
                ReportStatus.PASSED
                if document_count == 0 or chunk_count > 0
                else ReportStatus.WARNING
            ),
            message="Документы корпуса должны иметь обработанные чанки",
            actual=chunk_count,
            expected="> 0 when documents exist",
            required=False,
        )
    )
    return checks


async def _count_query(db: AsyncSession, statement: Executable) -> int:
    return int((await db.scalar(statement)) or 0)


def _zero(code: str, actual: int) -> CheckResult:
    return CheckResult(
        code=code,
        status=ReportStatus.PASSED if actual == 0 else ReportStatus.FAIL,
        message="Нарушений не обнаружено" if actual == 0 else "Обнаружены нарушения",
        actual=actual,
        expected=0,
    )
