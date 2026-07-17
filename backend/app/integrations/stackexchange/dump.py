from __future__ import annotations

import re
from collections.abc import Callable, Collection, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import IO, cast

from lxml import etree

from app.integrations.stackexchange.schemas import (
    StackExchangeAnswer,
    StackExchangeOwner,
    StackExchangeQuestion,
)

_TAG_PATTERN = re.compile(r"<([^<>]+)>")


@dataclass(frozen=True, slots=True)
class StackExchangeDumpThread:
    question: StackExchangeQuestion
    answers: tuple[StackExchangeAnswer, ...]


@dataclass(frozen=True, slots=True)
class DumpParseProgress:
    rows_scanned: int
    questions_matched: int
    answers_matched: int


@dataclass(frozen=True, slots=True)
class StackExchangeDumpSelection:
    threads: tuple[StackExchangeDumpThread, ...]
    rows_scanned: int
    questions_matched: int
    answers_matched: int
    owner_user_ids: frozenset[int]


def collect_question_threads(
    stream: IO[bytes],
    *,
    tag: str,
    existing_question_ids: Collection[int] = (),
    max_new_questions: int,
    answerless_only: bool = False,
    progress_every: int = 100_000,
    on_progress: Callable[[DumpParseProgress], None] | None = None,
) -> StackExchangeDumpSelection:
    """Select question threads from a Stack Exchange Posts.xml stream.

    Posts.xml is ordered by post id. Answers therefore appear after their parent
    question, which allows a single streaming pass without loading unrelated posts.
    """

    if max_new_questions < 1:
        raise ValueError("max_new_questions должен быть положительным")
    normalized_tag = tag.strip().casefold()
    if not normalized_tag:
        raise ValueError("tag не должен быть пустым")

    existing = set(existing_question_ids)
    questions: dict[int, StackExchangeQuestion] = {}
    answers: dict[int, list[StackExchangeAnswer]] = {}
    owner_user_ids: set[int] = set()
    rows_scanned = 0
    answers_matched = 0

    for attributes in _iter_rows(stream):
        rows_scanned += 1
        post_type = _optional_int(attributes.get("PostTypeId"))
        if post_type == 1 and len(questions) < max_new_questions:
            question_id = _optional_int(attributes.get("Id"))
            question_tags = parse_tags(attributes.get("Tags", ""))
            answer_count = _optional_int(attributes.get("AnswerCount")) or 0
            if (
                question_id is not None
                and question_id not in existing
                and normalized_tag in {item.casefold() for item in question_tags}
                and (not answerless_only or answer_count == 0)
            ):
                question = question_from_dump(attributes, tags=question_tags)
                questions[question.question_id] = question
                answers[question.question_id] = []
                _remember_owner(question.owner, owner_user_ids)
                if answerless_only and len(questions) >= max_new_questions:
                    break
        elif post_type == 2:
            parent_id = _optional_int(attributes.get("ParentId"))
            if parent_id is not None and parent_id in questions:
                answer = answer_from_dump(attributes)
                answers[parent_id].append(answer)
                answers_matched += 1
                _remember_owner(answer.owner, owner_user_ids)

        if on_progress is not None and progress_every > 0 and rows_scanned % progress_every == 0:
            on_progress(
                DumpParseProgress(
                    rows_scanned=rows_scanned,
                    questions_matched=len(questions),
                    answers_matched=answers_matched,
                )
            )

    threads = tuple(
        StackExchangeDumpThread(
            question=question,
            answers=tuple(
                item.model_copy(
                    update={
                        "is_accepted": question.accepted_answer_id == item.answer_id,
                    }
                )
                for item in answers[question_id]
            ),
        )
        for question_id, question in questions.items()
    )
    return StackExchangeDumpSelection(
        threads=threads,
        rows_scanned=rows_scanned,
        questions_matched=len(questions),
        answers_matched=answers_matched,
        owner_user_ids=frozenset(owner_user_ids),
    )


def collect_threads_by_question_ids(
    stream: IO[bytes],
    question_ids: Collection[int],
    *,
    progress_every: int = 100_000,
    on_progress: Callable[[DumpParseProgress], None] | None = None,
) -> StackExchangeDumpSelection:
    """Collect complete threads for known IDs regardless of XML row ordering.

    Stack Exchange dump rows are not guaranteed to be ordered by post ID.  Known
    parent IDs let us retain only relevant questions and answers in one bounded
    streaming pass, including answers that appear before their question row.
    """

    wanted = set(question_ids)
    if not wanted:
        return StackExchangeDumpSelection(
            threads=(),
            rows_scanned=0,
            questions_matched=0,
            answers_matched=0,
            owner_user_ids=frozenset(),
        )
    questions: dict[int, StackExchangeQuestion] = {}
    answers: dict[int, list[StackExchangeAnswer]] = {item: [] for item in wanted}
    owner_user_ids: set[int] = set()
    rows_scanned = 0
    answers_matched = 0
    for attributes in _iter_rows(stream):
        rows_scanned += 1
        post_type = _optional_int(attributes.get("PostTypeId"))
        if post_type == 1:
            question_id = _optional_int(attributes.get("Id"))
            if question_id in wanted:
                question = question_from_dump(attributes)
                questions[question.question_id] = question
                _remember_owner(question.owner, owner_user_ids)
        elif post_type == 2:
            parent_id = _optional_int(attributes.get("ParentId"))
            if parent_id in wanted:
                answer = answer_from_dump(attributes)
                answers[parent_id].append(answer)
                answers_matched += 1
                _remember_owner(answer.owner, owner_user_ids)
        if on_progress is not None and progress_every > 0 and rows_scanned % progress_every == 0:
            on_progress(
                DumpParseProgress(
                    rows_scanned=rows_scanned,
                    questions_matched=len(questions),
                    answers_matched=answers_matched,
                )
            )

    threads = tuple(
        StackExchangeDumpThread(
            question=question,
            answers=tuple(
                answer.model_copy(
                    update={"is_accepted": question.accepted_answer_id == answer.answer_id}
                )
                for answer in answers[question_id]
            ),
        )
        for question_id, question in questions.items()
    )
    return StackExchangeDumpSelection(
        threads=threads,
        rows_scanned=rows_scanned,
        questions_matched=len(threads),
        answers_matched=answers_matched,
        owner_user_ids=frozenset(owner_user_ids),
    )


def collect_user_display_names(
    stream: IO[bytes],
    user_ids: Collection[int],
) -> dict[int, str]:
    wanted = set(user_ids)
    names: dict[int, str] = {}
    if not wanted:
        return names
    for attributes in _iter_rows(stream):
        user_id = _optional_int(attributes.get("Id"))
        if user_id in wanted:
            display_name = attributes.get("DisplayName", "").strip()
            if display_name:
                names[user_id] = display_name
    return names


def hydrate_owner_names(
    selection: StackExchangeDumpSelection,
    names: dict[int, str],
) -> StackExchangeDumpSelection:
    threads = tuple(
        StackExchangeDumpThread(
            question=_with_owner_name(thread.question, names),
            answers=tuple(_with_owner_name(answer, names) for answer in thread.answers),
        )
        for thread in selection.threads
    )
    return StackExchangeDumpSelection(
        threads=threads,
        rows_scanned=selection.rows_scanned,
        questions_matched=selection.questions_matched,
        answers_matched=selection.answers_matched,
        owner_user_ids=selection.owner_user_ids,
    )


def parse_tags(value: str) -> list[str]:
    return [match.strip() for match in _TAG_PATTERN.findall(value) if match.strip()]


def question_from_dump(
    attributes: dict[str, str],
    *,
    tags: list[str] | None = None,
) -> StackExchangeQuestion:
    question_id = _required_int(attributes, "Id")
    creation_date = _required_timestamp(attributes, "CreationDate")
    last_activity_date = _optional_timestamp(attributes.get("LastActivityDate")) or creation_date
    accepted_answer_id = _optional_int(attributes.get("AcceptedAnswerId"))
    return StackExchangeQuestion(
        question_id=question_id,
        title=attributes.get("Title", ""),
        body=attributes.get("Body", ""),
        tags=tags if tags is not None else parse_tags(attributes.get("Tags", "")),
        link=f"https://ru.stackoverflow.com/questions/{question_id}",
        owner=_owner_from_dump(attributes),
        creation_date=creation_date,
        last_activity_date=last_activity_date,
        last_edit_date=_optional_timestamp(attributes.get("LastEditDate")),
        score=_optional_int(attributes.get("Score")) or 0,
        view_count=_optional_int(attributes.get("ViewCount")) or 0,
        answer_count=_optional_int(attributes.get("AnswerCount")) or 0,
        accepted_answer_id=accepted_answer_id,
        is_answered=accepted_answer_id is not None
        or (_optional_int(attributes.get("AnswerCount")) or 0) > 0,
        content_license=attributes.get("ContentLicense"),
    )


def answer_from_dump(attributes: dict[str, str]) -> StackExchangeAnswer:
    answer_id = _required_int(attributes, "Id")
    question_id = _required_int(attributes, "ParentId")
    creation_date = _required_timestamp(attributes, "CreationDate")
    return StackExchangeAnswer(
        answer_id=answer_id,
        question_id=question_id,
        body=attributes.get("Body", ""),
        owner=_owner_from_dump(attributes),
        creation_date=creation_date,
        last_activity_date=_optional_timestamp(attributes.get("LastActivityDate")) or creation_date,
        last_edit_date=_optional_timestamp(attributes.get("LastEditDate")),
        score=_optional_int(attributes.get("Score")) or 0,
        is_accepted=False,
        content_license=attributes.get("ContentLicense"),
    )


def _owner_from_dump(attributes: dict[str, str]) -> StackExchangeOwner | None:
    user_id = _optional_int(attributes.get("OwnerUserId"))
    display_name = attributes.get("OwnerDisplayName", "").strip()
    if user_id is None and not display_name:
        return None
    return StackExchangeOwner(
        user_id=user_id,
        display_name=display_name or (f"Пользователь {user_id}" if user_id is not None else ""),
        link=f"https://ru.stackoverflow.com/users/{user_id}" if user_id is not None else None,
    )


def _with_owner_name[ModelT: StackExchangeQuestion | StackExchangeAnswer](
    model: ModelT,
    names: dict[int, str],
) -> ModelT:
    owner = model.owner
    if owner is None or owner.user_id is None or owner.user_id not in names:
        return model
    return cast(
        ModelT,
        model.model_copy(
            update={
                "owner": owner.model_copy(update={"display_name": names[owner.user_id]}),
            }
        ),
    )


def _remember_owner(owner: StackExchangeOwner | None, result: set[int]) -> None:
    if owner is not None and owner.user_id is not None:
        result.add(owner.user_id)


def _required_int(attributes: dict[str, str], key: str) -> int:
    value = _optional_int(attributes.get(key))
    if value is None:
        raise ValueError(f"В dump отсутствует обязательное целое поле {key}")
    return value


def _optional_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError("В dump получено некорректное целое поле") from exc


def _required_timestamp(attributes: dict[str, str], key: str) -> int:
    value = _optional_timestamp(attributes.get(key))
    if value is None:
        raise ValueError(f"В dump отсутствует обязательная дата {key}")
    return value


def _optional_timestamp(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("В dump получена некорректная дата") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp())


def _iter_rows(stream: IO[bytes]) -> Iterator[dict[str, str]]:
    context = etree.iterparse(
        stream,
        events=("start", "end"),
        resolve_entities=False,
        no_network=True,
        huge_tree=True,
    )
    try:
        _, root = next(context)
    except StopIteration:
        return
    for event, element in context:
        if event == "end" and element.tag == "row":
            yield {str(key): str(value) for key, value in element.attrib.items()}
            element.clear()
            root.clear()
