from __future__ import annotations

from io import BytesIO

import pytest

from app.integrations.stackexchange.dump import (
    collect_question_threads,
    collect_threads_by_question_ids,
    collect_user_display_names,
    hydrate_owner_names,
    parse_tags,
)


def _stream(rows: str) -> BytesIO:
    return BytesIO(f'<?xml version="1.0" encoding="utf-8"?><posts>{rows}</posts>'.encode())


def test_dump_selects_python_threads_and_marks_accepted_answer() -> None:
    stream = _stream(
        """
        <row Id="10" PostTypeId="1" CreationDate="2024-01-01T10:00:00.000"
          LastActivityDate="2024-01-03T10:00:00.000" Score="5" ViewCount="100"
          Body="&lt;p&gt;Как сделать список?&lt;/p&gt;" OwnerUserId="7"
          Title="Списки Python" Tags="&lt;python&gt;&lt;list&gt;" AnswerCount="2"
          AcceptedAnswerId="12" ContentLicense="CC BY-SA 4.0" />
        <row Id="11" PostTypeId="1" CreationDate="2024-01-01T10:00:00.000"
          LastActivityDate="2024-01-01T10:00:00.000" Body="javascript"
          Title="JS" Tags="&lt;javascript&gt;" AnswerCount="0" />
        <row Id="12" PostTypeId="2" ParentId="10"
          CreationDate="2024-01-02T10:00:00.000"
          LastActivityDate="2024-01-02T10:00:00.000" Score="8"
          OwnerUserId="8" Body="&lt;p&gt;Используйте list&lt;/p&gt;"
          ContentLicense="CC BY-SA 4.0" />
        <row Id="13" PostTypeId="2" ParentId="10"
          CreationDate="2024-01-03T10:00:00.000"
          LastActivityDate="2024-01-03T10:00:00.000" Score="3"
          OwnerDisplayName="Удалённый автор"
          Body="&lt;pre&gt;&lt;code&gt;x = []&lt;/code&gt;&lt;/pre&gt;" />
        """
    )

    selection = collect_question_threads(stream, tag="python", max_new_questions=10)

    assert selection.questions_matched == 1
    assert selection.answers_matched == 2
    assert selection.owner_user_ids == frozenset({7, 8})
    thread = selection.threads[0]
    assert thread.question.question_id == 10
    assert thread.question.tags == ["python", "list"]
    assert thread.question.link == "https://ru.stackoverflow.com/questions/10"
    assert [answer.is_accepted for answer in thread.answers] == [True, False]
    assert thread.answers[1].owner is not None
    assert thread.answers[1].owner.display_name == "Удалённый автор"


def test_dump_skips_existing_questions_and_honours_limit() -> None:
    stream = _stream(
        """
        <row Id="1" PostTypeId="1" CreationDate="2024-01-01T00:00:00"
          Body="one" Title="One" Tags="&lt;python&gt;" AnswerCount="0" />
        <row Id="2" PostTypeId="1" CreationDate="2024-01-02T00:00:00"
          Body="two" Title="Two" Tags="&lt;python&gt;" AnswerCount="0" />
        <row Id="3" PostTypeId="1" CreationDate="2024-01-03T00:00:00"
          Body="three" Title="Three" Tags="&lt;python&gt;" AnswerCount="0" />
        """
    )

    selection = collect_question_threads(
        stream,
        tag="PYTHON",
        existing_question_ids={1},
        max_new_questions=1,
    )

    assert [thread.question.question_id for thread in selection.threads] == [2]


def test_dump_can_stop_after_answerless_fill_candidates() -> None:
    stream = _stream(
        """
        <row Id="1" PostTypeId="1" CreationDate="2024-01-01T00:00:00"
          Body="answered" Title="Answered" Tags="&lt;python&gt;" AnswerCount="1" />
        <row Id="2" PostTypeId="1" CreationDate="2024-01-02T00:00:00"
          Body="first" Title="First" Tags="&lt;python&gt;" AnswerCount="0" />
        <row Id="3" PostTypeId="1" CreationDate="2024-01-03T00:00:00"
          Body="second" Title="Second" Tags="&lt;python&gt;" AnswerCount="0" />
        <row Id="4" PostTypeId="1" CreationDate="2024-01-04T00:00:00"
          Body="not scanned" Title="Third" Tags="&lt;python&gt;" AnswerCount="0" />
        """
    )

    selection = collect_question_threads(
        stream,
        tag="python",
        max_new_questions=2,
        answerless_only=True,
    )

    assert [thread.question.question_id for thread in selection.threads] == [2, 3]
    assert selection.rows_scanned == 3


def test_dump_collects_answers_that_precede_question_rows() -> None:
    stream = _stream(
        """
        <row Id="12" PostTypeId="2" ParentId="10"
          CreationDate="2024-01-02T10:00:00.000" Score="8" Body="accepted" />
        <row Id="13" PostTypeId="2" ParentId="99"
          CreationDate="2024-01-02T10:00:00.000" Body="unrelated" />
        <row Id="10" PostTypeId="1" CreationDate="2024-01-01T10:00:00.000"
          Body="question" Title="Question" Tags="&lt;python&gt;" AnswerCount="1"
          AcceptedAnswerId="12" />
        """
    )

    selection = collect_threads_by_question_ids(stream, {10})

    assert selection.questions_matched == 1
    assert selection.answers_matched == 1
    assert selection.threads[0].answers[0].answer_id == 12
    assert selection.threads[0].answers[0].is_accepted is True


def test_dump_hydrates_registered_user_names() -> None:
    posts = _stream(
        """
        <row Id="10" PostTypeId="1" CreationDate="2024-01-01T00:00:00"
          Body="question" OwnerUserId="7" Title="Question"
          Tags="&lt;python&gt;" AnswerCount="1" />
        <row Id="11" PostTypeId="2" ParentId="10"
          CreationDate="2024-01-02T00:00:00" Body="answer" OwnerUserId="8" />
        """
    )
    users = BytesIO(
        b'<?xml version="1.0"?><users>'
        b'<row Id="7" DisplayName="Alice" />'
        b'<row Id="8" DisplayName="Bob" />'
        b"</users>"
    )
    selection = collect_question_threads(posts, tag="python", max_new_questions=10)
    names = collect_user_display_names(users, selection.owner_user_ids)

    hydrated = hydrate_owner_names(selection, names)

    assert hydrated.threads[0].question.owner is not None
    assert hydrated.threads[0].question.owner.display_name == "Alice"
    assert hydrated.threads[0].answers[0].owner is not None
    assert hydrated.threads[0].answers[0].owner.display_name == "Bob"


def test_parse_tags_and_validation() -> None:
    assert parse_tags("<python><asyncio><python-3.x>") == ["python", "asyncio", "python-3.x"]
    with pytest.raises(ValueError, match="положительным"):
        collect_question_threads(_stream(""), tag="python", max_new_questions=0)
