from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import IO
from uuid import UUID

from sqlalchemy import exists, func, select

from app.core.config import Settings, get_settings
from app.core.enums import IngestionResultStatus
from app.db.base import utc_now
from app.db.models import Answer, Document, Source, SourceSyncState
from app.db.session import SessionFactory, engine
from app.integrations.stackexchange.dump import (
    DumpParseProgress,
    StackExchangeDumpSelection,
    StackExchangeDumpThread,
    collect_question_threads,
    collect_threads_by_question_ids,
    collect_user_display_names,
    hydrate_owner_names,
)
from app.services.document_ingestion import (
    IngestionSkip,
    ingest_question_thread,
)

_SOURCE_REPO_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = _SOURCE_REPO_ROOT if (_SOURCE_REPO_ROOT / "backend").is_dir() else Path.cwd()
ARTIFACTS_DIR = Path(os.environ.get("ARTIFACTS_DIR", REPO_ROOT / "artifacts"))


@dataclass(slots=True)
class ImportCounters:
    processed: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    duplicates: int = 0
    skipped: int = 0
    failed: int = 0
    chunks_created: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SourceContext:
    source_id: UUID
    existing_ids: frozenset[int]
    documents_count: int
    target_documents: int
    dump_import: dict[str, object]
    answer_gap_ids: frozenset[int]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Импорт официального Stack Exchange Data Dump через существующий PyAnswer pipeline"
        )
    )
    parser.add_argument("archive", type=Path, help="Путь к ru.stackoverflow.com.7z")
    parser.add_argument("--source-id", type=UUID)
    parser.add_argument("--site", default="ru.stackoverflow")
    parser.add_argument("--tag", default="python")
    parser.add_argument("--target-total", type=int)
    parser.add_argument("--max-new", type=int)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--max-failures", type=int, default=25)
    parser.add_argument(
        "--repair-answer-gaps",
        action="store_true",
        help="Повторно обработать документы с неполным набором ответов из dump",
    )
    parser.add_argument(
        "--seven-zip-bin",
        default=os.environ.get("SEVEN_ZIP_BIN", "7z"),
        help="Путь к 7z/7zz",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=ARTIFACTS_DIR / "raw/stackexchange/dump-import-report.json",
    )
    parser.add_argument(
        "--parse-only",
        action="store_true",
        help="Проверить и разобрать dump без записи в PostgreSQL",
    )
    return parser


async def run(args: argparse.Namespace) -> dict[str, object]:
    settings = get_settings()
    archive = args.archive.expanduser().resolve()
    if not archive.is_file():
        raise FileNotFoundError(f"Архив не найден: {archive}")
    seven_zip = _resolve_executable(args.seven_zip_bin)
    if not 1 <= args.concurrency <= 16:
        raise ValueError("concurrency должен быть в диапазоне 1..16")
    if args.max_failures < 1:
        raise ValueError("max-failures должен быть положительным")

    source_context = await _load_source_context(
        source_id=args.source_id,
        site=args.site,
        tag=args.tag,
    )
    target_total = args.target_total or source_context.target_documents
    if target_total < source_context.documents_count:
        target_total = source_context.documents_count
    if args.repair_answer_gaps:
        repair_ids = source_context.answer_gap_ids
        if not repair_ids:
            repair_report = {
                "status": "NOTHING_TO_REPAIR",
                "archive": archive.name,
                "sourceId": str(source_context.source_id),
                "documentsAfter": source_context.documents_count,
                "answerGapDocuments": 0,
            }
            _write_report(args.report, repair_report)
            return repair_report
        started_at = utc_now()
        started = monotonic()
        print(f"Восстановление ответов для {len(repair_ids)} документов", flush=True)
        selection = await asyncio.to_thread(
            _read_known_selection,
            archive,
            seven_zip,
            repair_ids,
        )
        counters = ImportCounters()
        if not args.parse_only:
            counters = await _import_selection(
                selection,
                source_id=source_context.source_id,
                settings=settings,
                concurrency=args.concurrency,
                max_failures=args.max_failures,
            )
        documents_after = await _document_count(source_context.source_id)
        repair_report = {
            "status": "PARSED" if args.parse_only else "REPAIRED",
            "archive": archive.name,
            "archiveBytes": archive.stat().st_size,
            "site": args.site,
            "tag": args.tag,
            "sourceId": str(source_context.source_id),
            "startedAt": started_at.isoformat(),
            "finishedAt": utc_now().isoformat(),
            "durationSeconds": round(monotonic() - started, 3),
            "answerGapDocuments": len(repair_ids),
            "questionsSelected": selection.questions_matched,
            "answersSelected": selection.answers_matched,
            "documentsAfter": documents_after,
            "parseOnly": bool(args.parse_only),
            **asdict(counters),
        }
        _write_report(args.report, repair_report)
        return repair_report
    needed = max(0, target_total - source_context.documents_count)
    if args.max_new is not None:
        if args.max_new < 1:
            raise ValueError("max-new должен быть положительным")
        needed = min(needed, args.max_new)
    if needed == 0:
        existing_report: dict[str, object] = {
            "status": "NOTHING_TO_IMPORT",
            "archive": archive.name,
            "archiveBytes": archive.stat().st_size,
            "site": args.site,
            "tag": args.tag,
            "sourceId": str(source_context.source_id),
            "documentsBefore": source_context.documents_count,
            "documentsAfter": source_context.documents_count,
            "targetTotal": target_total,
            "dumpImport": source_context.dump_import,
        }
        _write_report(args.report, existing_report)
        return existing_report

    started_at = utc_now()
    started = monotonic()
    print(
        f"Разбор {archive.name}: нужно добавить до {needed} вопросов с меткой {args.tag}",
        flush=True,
    )
    fast_answerless_fill = needed <= 100
    selection_limit = needed + 10 if fast_answerless_fill else needed
    selection = await asyncio.to_thread(
        _read_selection,
        archive,
        seven_zip,
        args.tag,
        source_context.existing_ids,
        selection_limit,
        fast_answerless_fill,
    )
    print(
        f"Выбрано вопросов: {selection.questions_matched}; ответов: "
        f"{selection.answers_matched}; строк просмотрено: {selection.rows_scanned}",
        flush=True,
    )

    counters = ImportCounters()
    if not args.parse_only:
        counters = await _import_selection(
            selection,
            source_id=source_context.source_id,
            settings=settings,
            concurrency=args.concurrency,
            max_failures=args.max_failures,
        )
        documents_after = await _finalize_source(
            source_context.source_id,
            selection,
            counters,
            target_total=target_total,
            archive=archive,
        )
    else:
        documents_after = source_context.documents_count

    report: dict[str, object] = {
        "status": "PARSED" if args.parse_only else "COMPLETED",
        "archive": archive.name,
        "archiveBytes": archive.stat().st_size,
        "site": args.site,
        "tag": args.tag,
        "sourceId": str(source_context.source_id),
        "startedAt": started_at.isoformat(),
        "finishedAt": utc_now().isoformat(),
        "durationSeconds": round(monotonic() - started, 3),
        "rowsScanned": selection.rows_scanned,
        "questionsSelected": selection.questions_matched,
        "answersSelected": selection.answers_matched,
        "documentsBefore": source_context.documents_count,
        "documentsAfter": documents_after,
        "targetTotal": target_total,
        "parseOnly": bool(args.parse_only),
        **asdict(counters),
    }
    _write_report(args.report, report)
    return report


def _read_selection(
    archive: Path,
    seven_zip: Path,
    tag: str,
    existing_ids: frozenset[int],
    needed: int,
    fast_answerless_fill: bool = False,
) -> StackExchangeDumpSelection:
    with _archive_member(
        archive,
        seven_zip,
        "Posts.xml",
        allow_early_close=fast_answerless_fill,
    ) as stream:
        selection = collect_question_threads(
            stream,
            tag=tag,
            existing_question_ids=existing_ids,
            max_new_questions=needed,
            answerless_only=fast_answerless_fill,
            on_progress=_print_parse_progress,
        )
    if not fast_answerless_fill:
        question_ids = frozenset(thread.question.question_id for thread in selection.threads)
        print("Повторный проход Posts.xml для полного набора ответов…", flush=True)
        with _archive_member(archive, seven_zip, "Posts.xml") as stream:
            selection = collect_threads_by_question_ids(
                stream,
                question_ids,
                on_progress=_print_parse_progress,
            )
    print(f"Разрешение имён {len(selection.owner_user_ids)} авторов…", flush=True)
    with _archive_member(archive, seven_zip, "Users.xml") as stream:
        names = collect_user_display_names(stream, selection.owner_user_ids)
    return hydrate_owner_names(selection, names)


def _read_known_selection(
    archive: Path,
    seven_zip: Path,
    question_ids: frozenset[int],
) -> StackExchangeDumpSelection:
    with _archive_member(archive, seven_zip, "Posts.xml") as stream:
        selection = collect_threads_by_question_ids(
            stream,
            question_ids,
            on_progress=_print_parse_progress,
        )
    print(f"Разрешение имён {len(selection.owner_user_ids)} авторов…", flush=True)
    with _archive_member(archive, seven_zip, "Users.xml") as stream:
        names = collect_user_display_names(stream, selection.owner_user_ids)
    return hydrate_owner_names(selection, names)


def _print_parse_progress(progress: DumpParseProgress) -> None:
    print(
        f"XML: {progress.rows_scanned} строк; вопросы {progress.questions_matched}; "
        f"ответы {progress.answers_matched}",
        flush=True,
    )


@contextmanager
def _archive_member(
    archive: Path,
    seven_zip: Path,
    member: str,
    *,
    allow_early_close: bool = False,
) -> Iterator[IO[bytes]]:
    if member not in {"Posts.xml", "Users.xml"}:
        raise ValueError("Недопустимый member архива")
    process = subprocess.Popen(  # noqa: S603 - executable and member are validated local paths
        [str(seven_zip), "x", "-so", str(archive), member],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.stdout is None or process.stderr is None:
        process.kill()
        raise RuntimeError("Не удалось открыть поток 7z")
    try:
        yield process.stdout
    finally:
        process.stdout.close()
        terminated_early = allow_early_close and process.poll() is None
        if terminated_early:
            process.terminate()
        stderr = process.stderr.read().decode("utf-8", errors="replace")
        return_code = process.wait(timeout=60)
        process.stderr.close()
        if return_code != 0 and not terminated_early:
            safe_message = stderr.strip().splitlines()[-1] if stderr.strip() else "unknown error"
            raise RuntimeError(f"7z не смог прочитать {member}: {safe_message}")


async def _load_source_context(
    *,
    source_id: UUID | None,
    site: str,
    tag: str,
) -> SourceContext:
    async with SessionFactory() as session:
        statement = select(Source)
        if source_id is not None:
            statement = statement.where(Source.id == source_id)
        else:
            statement = statement.where(Source.site == site, Source.tag == tag)
        source = await session.scalar(statement.limit(1))
        if source is None:
            raise LookupError("Источник Stack Exchange не найден")
        state = await session.get(SourceSyncState, source.id)
        raw_dump_import = (state.state or {}).get("dataDumpImport") if state is not None else None
        dump_import = dict(raw_dump_import) if isinstance(raw_dump_import, dict) else {}
        raw_ids = (
            await session.scalars(
                select(Document.external_id).where(Document.source_id == source.id)
            )
        ).all()
        stored_answer_count = (
            select(func.count(Answer.id))
            .where(
                Answer.document_id == Document.id,
                Answer.source_missing.is_(False),
            )
            .correlate(Document)
            .scalar_subquery()
        )
        accepted_exists = exists().where(
            Answer.document_id == Document.id,
            Answer.external_id == Document.accepted_answer_external_id,
            Answer.is_accepted.is_(True),
        )
        raw_gap_ids = (
            await session.scalars(
                select(Document.external_id).where(
                    Document.source_id == source.id,
                    (Document.answers_count > stored_answer_count)
                    | (Document.accepted_answer_external_id.is_not(None) & ~accepted_exists),
                )
            )
        ).all()
    existing_ids = frozenset(int(item) for item in raw_ids if item.isdecimal())
    answer_gap_ids = frozenset(int(item) for item in raw_gap_ids if item.isdecimal())
    return SourceContext(
        source_id=source.id,
        existing_ids=existing_ids,
        documents_count=len(raw_ids),
        target_documents=source.target_documents,
        dump_import=dump_import,
        answer_gap_ids=answer_gap_ids,
    )


async def _document_count(source_id: UUID) -> int:
    async with SessionFactory() as session:
        return int(
            await session.scalar(
                select(func.count()).select_from(Document).where(Document.source_id == source_id)
            )
            or 0
        )


async def _import_selection(
    selection: StackExchangeDumpSelection,
    *,
    source_id: UUID,
    settings: Settings,
    concurrency: int,
    max_failures: int,
) -> ImportCounters:
    queue: asyncio.Queue[StackExchangeDumpThread | None] = asyncio.Queue()
    for thread in selection.threads:
        queue.put_nowait(thread)
    for _ in range(concurrency):
        queue.put_nowait(None)

    counters = ImportCounters()
    lock = asyncio.Lock()
    stop = asyncio.Event()
    total = len(selection.threads)

    async def worker() -> None:
        while True:
            thread = await queue.get()
            try:
                if thread is None:
                    return
                if stop.is_set():
                    continue
                try:
                    async with SessionFactory() as session, session.begin():
                        source = await session.get(Source, source_id)
                        if source is None:
                            raise LookupError("Источник Stack Exchange исчез во время импорта")
                        result = await ingest_question_thread(
                            session,
                            source,
                            thread.question,
                            list(thread.answers),
                            settings=settings,
                        )
                except IngestionSkip as exc:
                    async with lock:
                        counters.processed += 1
                        counters.skipped += 1
                        _remember_error(counters, thread, exc.code, exc.safe_message)
                except Exception as exc:
                    async with lock:
                        counters.processed += 1
                        counters.failed += 1
                        _remember_error(
                            counters,
                            thread,
                            type(exc).__name__,
                            str(exc)[:300],
                        )
                        if counters.failed >= max_failures:
                            stop.set()
                else:
                    async with lock:
                        counters.processed += 1
                        counters.chunks_created += result.chunks_created
                        if result.status == IngestionResultStatus.INSERTED:
                            counters.inserted += 1
                        elif result.status == IngestionResultStatus.UPDATED:
                            counters.updated += 1
                        elif result.status == IngestionResultStatus.UNCHANGED:
                            counters.unchanged += 1
                        elif result.status == IngestionResultStatus.DUPLICATE:
                            counters.duplicates += 1
                async with lock:
                    if counters.processed % 100 == 0 or counters.processed == total:
                        print(
                            f"Импорт: {counters.processed}/{total}; inserted={counters.inserted}; "
                            f"duplicate={counters.duplicates}; skipped={counters.skipped}; "
                            f"failed={counters.failed}; chunks={counters.chunks_created}",
                            flush=True,
                        )
            finally:
                queue.task_done()

    workers = [asyncio.create_task(worker()) for _ in range(concurrency)]
    await queue.join()
    await asyncio.gather(*workers)
    if stop.is_set():
        raise RuntimeError(
            f"Импорт остановлен после {counters.failed} ошибок; безопасные commits сохранены"
        )
    return counters


def _remember_error(
    counters: ImportCounters,
    thread: StackExchangeDumpThread,
    code: str,
    message: str,
) -> None:
    if len(counters.errors) < 100:
        counters.errors.append(
            {
                "questionId": str(thread.question.question_id),
                "code": code[:80],
                "message": message[:500],
            }
        )


async def _finalize_source(
    source_id: UUID,
    selection: StackExchangeDumpSelection,
    counters: ImportCounters,
    *,
    target_total: int,
    archive: Path,
) -> int:
    now = utc_now()
    latest_activity = max(
        (
            datetime.fromtimestamp(thread.question.last_activity_date, UTC)
            for thread in selection.threads
        ),
        default=None,
    )
    async with SessionFactory() as session, session.begin():
        source = await session.get(Source, source_id, with_for_update=True)
        if source is None:
            raise LookupError("Источник Stack Exchange не найден при завершении импорта")
        count = int(
            await session.scalar(
                select(func.count()).select_from(Document).where(Document.source_id == source_id)
            )
            or 0
        )
        source.documents_count = count
        source.last_sync_at = now
        if counters.failed == 0:
            source.last_successful_sync_at = now

        state = await session.get(SourceSyncState, source_id, with_for_update=True)
        if state is None:
            state = SourceSyncState(source_id=source_id, next_page=1, state={})
            session.add(state)
        state.last_checkpoint_at = now
        state.total_questions_fetched += selection.questions_matched
        state.total_answers_fetched += selection.answers_matched
        state.total_documents_inserted += counters.inserted
        state.total_documents_updated += counters.updated
        state.total_documents_unchanged += counters.unchanged
        state.total_exact_duplicates += counters.duplicates
        state.total_items_skipped += counters.skipped
        state.total_errors += counters.failed
        state.total_chunks_created += counters.chunks_created
        if latest_activity is not None:
            if (
                state.last_seen_question_activity_at is None
                or latest_activity > state.last_seen_question_activity_at
            ):
                state.last_seen_question_activity_at = latest_activity
        previous_state = dict(state.state or {})
        previous_dump = previous_state.get("dataDumpImport")
        previous_dump = dict(previous_dump) if isinstance(previous_dump, dict) else {}
        previous_state["dataDumpImport"] = {
            "archive": archive.name,
            "completedAt": now.isoformat(),
            "imports": _nonnegative_int(previous_dump.get("imports")) + 1,
            "questions": _nonnegative_int(previous_dump.get("questions"))
            + selection.questions_matched,
            "answers": _nonnegative_int(previous_dump.get("answers")) + selection.answers_matched,
            "inserted": _nonnegative_int(previous_dump.get("inserted")) + counters.inserted,
            "updated": _nonnegative_int(previous_dump.get("updated")) + counters.updated,
            "unchanged": _nonnegative_int(previous_dump.get("unchanged")) + counters.unchanged,
            "duplicates": _nonnegative_int(previous_dump.get("duplicates")) + counters.duplicates,
            "skipped": _nonnegative_int(previous_dump.get("skipped")) + counters.skipped,
            "failed": _nonnegative_int(previous_dump.get("failed")) + counters.failed,
            "chunksCreated": _nonnegative_int(previous_dump.get("chunksCreated"))
            + counters.chunks_created,
            "documentsAfter": count,
        }
        state.state = previous_state
        if count >= target_total and counters.failed == 0:
            state.initial_sync_completed_at = state.initial_sync_completed_at or now
            if latest_activity is not None and (
                state.incremental_watermark is None or latest_activity > state.incremental_watermark
            ):
                state.incremental_watermark = latest_activity
    return count


def _resolve_executable(value: str) -> Path:
    candidate = Path(value).expanduser()
    resolved = candidate.resolve() if candidate.is_absolute() else None
    if resolved is None:
        found = shutil.which(value)
        resolved = Path(found).resolve() if found else None
    if resolved is None or not resolved.is_file():
        raise FileNotFoundError("7z не найден; установите пакет 7zip или задайте --seven-zip-bin")
    return resolved


def _nonnegative_int(value: object) -> int:
    return value if type(value) is int and value >= 0 else 0


def _write_report(path: Path, report: dict[str, object]) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    print(f"Отчёт: {path}", flush=True)


async def main() -> None:
    args = build_parser().parse_args()
    try:
        report = await run(args)
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
