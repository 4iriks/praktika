from __future__ import annotations

import warnings

from app.integrations.stackexchange.schemas import StackExchangeAnswer, StackExchangeQuestion
from app.processing.canonical import build_canonical_document
from app.processing.html import CleanedContent, ContentBlock, clean_html, clean_title
from app.processing.selection import ProcessedAnswer, select_corpus_answers


def cleaned(text: str) -> CleanedContent:
    return CleanedContent(
        text=text,
        sanitized_html=f"<p>{text}</p>",
        blocks=(ContentBlock("paragraph", text),) if text else (),
        has_code=False,
    )


def question(
    *, accepted_id: int | None = 1, tags: list[str] | None = None
) -> StackExchangeQuestion:
    return StackExchangeQuestion(
        question_id=100,
        title="Как &lt;правильно&gt;?",
        body="<p>Вопрос</p>",
        tags=tags or ["python", "asyncio"],
        link="https://ru.stackoverflow.com/questions/100/example",
        creation_date=1_700_000_000,
        last_activity_date=1_700_000_100,
        score=5,
        view_count=20,
        answer_count=5,
        accepted_answer_id=accepted_id,
        is_answered=accepted_id is not None,
    )


def answer(
    answer_id: int,
    score: int,
    creation_date: int,
    *,
    text: str | None = None,
    accepted: bool = False,
    source_missing: bool = False,
) -> ProcessedAnswer:
    dto = StackExchangeAnswer(
        answer_id=answer_id,
        question_id=100,
        body=f"<p>{text or answer_id}</p>",
        creation_date=creation_date,
        last_activity_date=creation_date + 1,
        score=score,
        is_accepted=accepted,
    )
    return ProcessedAnswer(dto, cleaned(str(answer_id) if text is None else text), source_missing)


def test_html_cleaner_removes_xss_and_preserves_structure_and_code() -> None:
    code = "def check(value):\r\n    return value &lt;= 10 &amp; value != 0"
    value = f"""
    <h2>Заголовок &amp; детали</h2>
    <script>alert(1)</script><iframe src="https://evil.invalid"></iframe>
    <p onclick="steal()">Текст с <code>a &lt; b</code> и
      <a href="javascript:alert(1)">опасной ссылкой</a>.</p>
    <ul><li>Первый</li><li>Второй</li></ul>
    <blockquote>Цитата</blockquote>
    <pre><code class="language-python">{code}</code></pre>
    """
    result = clean_html(
        value,
        maximum_input_bytes=100_000,
        maximum_output_characters=100_000,
    )

    assert "alert(1)" not in result.text
    assert "iframe" not in result.sanitized_html
    assert "onclick" not in result.sanitized_html
    assert "javascript:" not in result.sanitized_html
    assert "## Заголовок & детали" in result.text
    assert "`a < b`" in result.text
    assert "- Первый\n- Второй" in result.text
    assert "> Цитата" in result.text
    assert "```python" in result.text
    assert "    return value <= 10 & value != 0" in result.text
    assert result.has_code is True


def test_html_normalization_is_unicode_and_line_ending_deterministic() -> None:
    decomposed = "<p>Cafe\u0301&nbsp;Python</p><pre><code>if x:\r\n    print('✓')</code></pre>"
    first = clean_html(
        decomposed,
        maximum_input_bytes=10_000,
        maximum_output_characters=10_000,
    )
    second = clean_html(
        decomposed.replace("\r\n", "\n"),
        maximum_input_bytes=10_000,
        maximum_output_characters=10_000,
    )
    assert first.text == second.text
    assert "Café Python" in first.text
    assert "    print('✓')" in first.text
    assert clean_title("<b>  A &amp; B </b>") == "A & B"


def test_title_that_looks_like_path_does_not_emit_parser_warning() -> None:
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        assert clean_title("requirements.txt") == "requirements.txt"
    assert captured == []


def test_answer_selection_is_stable_and_never_duplicates_accepted() -> None:
    answers = [
        answer(1, 1, 20, accepted=True),
        answer(2, 10, 30),
        answer(3, 10, 10),
        answer(4, 10, 10),
        answer(5, 100, 1),
    ]
    selection = select_corpus_answers(question(), answers, max_additional_answers=3)
    assert [item.answer.source.answer_id for item in selection.selected] == [1, 5, 3, 4]
    assert selection.selected[0].accepted is True
    assert len({item.answer.source.answer_id for item in selection.selected}) == 4
    assert selection.missing_accepted is False


def test_selection_without_accepted_uses_four_and_excludes_empty_missing() -> None:
    answers = [
        answer(1, 8, 1, text=""),
        answer(2, 7, 2, source_missing=True),
        answer(3, 6, 3),
        answer(4, 5, 4),
        answer(5, 4, 5),
        answer(6, 3, 6),
        answer(7, 2, 7),
    ]
    selection = select_corpus_answers(
        question(accepted_id=None),
        answers,
        max_additional_answers=3,
    )
    assert [item.answer.source.answer_id for item in selection.selected] == [3, 4, 5, 6]
    assert all(not item.accepted for item in selection.selected)


def test_missing_declared_accepted_is_reported_without_substitution() -> None:
    selection = select_corpus_answers(
        question(accepted_id=999),
        [answer(2, 10, 1), answer(3, 5, 2)],
        max_additional_answers=3,
    )
    assert selection.missing_accepted is True
    assert all(not item.accepted for item in selection.selected)


def test_canonical_hash_ignores_metadata_and_tag_order_but_tracks_content() -> None:
    base_question = question(tags=["python", "asyncio", "python"])
    selection = select_corpus_answers(
        base_question,
        [answer(1, 5, 1, text="Ответ")],
        max_additional_answers=3,
    )
    first = build_canonical_document(
        base_question,
        title="Заголовок",
        question_content=cleaned("Текст вопроса"),
        selection=selection,
    )
    changed_metadata = base_question.model_copy(
        update={"tags": ["asyncio", "python"], "score": 900, "view_count": 1000}
    )
    second = build_canonical_document(
        changed_metadata,
        title="Заголовок",
        question_content=cleaned("Текст вопроса"),
        selection=selection,
    )
    changed_content = build_canonical_document(
        base_question,
        title="Заголовок",
        question_content=cleaned("Другой вопрос"),
        selection=selection,
    )

    assert first.content_hash == second.content_hash
    assert first.metadata_hash != second.metadata_hash
    assert first.content_hash != changed_content.content_hash
    assert first.tags == ("asyncio", "python")
    assert "## Принятый ответ" in first.text
