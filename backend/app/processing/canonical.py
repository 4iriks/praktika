from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass

from app.core.enums import ChunkSectionType
from app.integrations.stackexchange.schemas import StackExchangeQuestion
from app.processing.html import CleanedContent
from app.processing.selection import AnswerSelection


@dataclass(frozen=True, slots=True)
class CanonicalSection:
    section_type: ChunkSectionType
    label: str
    text: str
    answer_external_id: str | None = None


@dataclass(frozen=True, slots=True)
class CanonicalDocument:
    title: str
    tags: tuple[str, ...]
    sections: tuple[CanonicalSection, ...]
    text: str
    content_hash: str
    metadata_hash: str


def normalize_tags(tags: list[str]) -> tuple[str, ...]:
    normalized = {
        unicodedata.normalize("NFC", tag).strip().casefold()[:100]
        for tag in tags
        if unicodedata.normalize("NFC", tag).strip()
    }
    return tuple(sorted(normalized))


def stable_sha256(value: object) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def build_canonical_document(
    question: StackExchangeQuestion,
    *,
    title: str,
    question_content: CleanedContent,
    selection: AnswerSelection,
) -> CanonicalDocument:
    tags = normalize_tags(question.tags)
    sections: list[CanonicalSection] = [
        CanonicalSection(ChunkSectionType.QUESTION, "Вопрос", question_content.text)
    ]
    additional_index = 0
    for selected in selection.selected:
        if selected.accepted:
            section_type = ChunkSectionType.ACCEPTED_ANSWER
            label = "Принятый ответ"
        else:
            additional_index += 1
            section_type = ChunkSectionType.ANSWER
            label = f"Дополнительный ответ {additional_index}"
        sections.append(
            CanonicalSection(
                section_type,
                label,
                selected.answer.content.text,
                str(selected.answer.source.answer_id),
            )
        )
    text_parts = [f"# {title}", f"Теги: {', '.join(tags)}"]
    for section in sections:
        text_parts.extend((f"## {section.label}", section.text))
    canonical_text = "\n\n".join(part for part in text_parts if part).strip()
    content_payload = {
        "title": title,
        "tags": tags,
        "sections": [
            {
                "type": section.section_type.value,
                "text": section.text,
            }
            for section in sections
        ],
    }
    metadata_payload = {
        "questionId": question.question_id,
        "author": question.owner.display_name if question.owner else "",
        "creationDate": question.creation_date,
        "lastActivityDate": question.last_activity_date,
        "lastEditDate": question.last_edit_date,
        "score": question.score,
        "views": question.view_count,
        "answerCount": question.answer_count,
        "isAnswered": question.is_answered,
        "selectedAnswers": [
            {
                "answerId": selected.answer.source.answer_id,
                "score": selected.answer.source.score,
                "lastActivityDate": selected.answer.source.last_activity_date,
                "lastEditDate": selected.answer.source.last_edit_date,
            }
            for selected in selection.selected
        ],
    }
    return CanonicalDocument(
        title=title,
        tags=tags,
        sections=tuple(sections),
        text=canonical_text,
        content_hash=stable_sha256(content_payload),
        metadata_hash=stable_sha256(metadata_payload),
    )
