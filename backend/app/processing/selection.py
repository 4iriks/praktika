from __future__ import annotations

from dataclasses import dataclass

from app.integrations.stackexchange.schemas import StackExchangeAnswer, StackExchangeQuestion
from app.processing.html import CleanedContent


@dataclass(frozen=True, slots=True)
class ProcessedAnswer:
    source: StackExchangeAnswer
    content: CleanedContent
    source_missing: bool = False


@dataclass(frozen=True, slots=True)
class SelectedCorpusAnswer:
    answer: ProcessedAnswer
    rank: int
    accepted: bool


@dataclass(frozen=True, slots=True)
class AnswerSelection:
    selected: tuple[SelectedCorpusAnswer, ...]
    missing_accepted: bool


def select_corpus_answers(
    question: StackExchangeQuestion,
    answers: list[ProcessedAnswer],
    *,
    max_additional_answers: int,
) -> AnswerSelection:
    if not 0 <= max_additional_answers <= 3:
        raise ValueError("max_additional_answers должен находиться в диапазоне 0..3")
    candidates = [
        item for item in answers if not item.source_missing and bool(item.content.text.strip())
    ]
    declared_id = question.accepted_answer_id
    accepted: ProcessedAnswer | None = None
    missing_accepted = False
    if declared_id is not None:
        accepted = next(
            (item for item in candidates if item.source.answer_id == declared_id),
            None,
        )
        missing_accepted = accepted is None
    else:
        flagged = [item for item in candidates if item.source.is_accepted]
        accepted = min(flagged, key=lambda item: item.source.answer_id) if flagged else None

    additional = [item for item in candidates if item is not accepted]
    additional.sort(
        key=lambda item: (
            -item.source.score,
            item.source.creation_date,
            item.source.answer_id,
        )
    )
    selected: list[SelectedCorpusAnswer] = []
    if accepted is not None:
        selected.append(SelectedCorpusAnswer(accepted, rank=1, accepted=True))
        limit = max_additional_answers
    else:
        limit = max_additional_answers + 1
    selected.extend(
        SelectedCorpusAnswer(item, rank=len(selected) + 1, accepted=False)
        for item in additional[:limit]
    )
    return AnswerSelection(tuple(selected), missing_accepted)
