from __future__ import annotations

from uuid import UUID

from app.core.enums import ChunkSectionType
from app.processing.canonical import CanonicalDocument, CanonicalSection
from app.processing.chunking import (
    ChunkingSettings,
    DocumentChunker,
    stable_chunk_key,
)


def canonical(*sections: CanonicalSection) -> CanonicalDocument:
    return CanonicalDocument(
        title="Детерминированный chunker",
        tags=("python", "asyncio"),
        sections=sections,
        text="",
        content_hash="a" * 64,
        metadata_hash="b" * 64,
    )


def chunker() -> DocumentChunker:
    return DocumentChunker(
        ChunkingSettings(target_tokens=18, max_tokens=28, overlap_tokens=4, min_tokens=3)
    )


def test_chunking_is_deterministic_bounded_and_contextual() -> None:
    document = canonical(
        CanonicalSection(
            ChunkSectionType.QUESTION,
            "Вопрос",
            "Первый абзац содержит несколько важных слов для проверки разбиения.\n\n"
            "Второй абзац также содержит достаточно слов и завершает постановку задачи.",
        ),
        CanonicalSection(
            ChunkSectionType.ACCEPTED_ANSWER,
            "Принятый ответ",
            "Короткий, но полезный ответ.",
            "42",
        ),
    )
    first = chunker().chunk(document)
    second = chunker().chunk(document)

    assert first == second
    assert first
    assert all(item.text and item.token_count <= 28 for item in first)
    assert all("Детерминированный chunker" in item.contextual_text for item in first)
    assert all("python, asyncio" in item.contextual_text for item in first)
    assert first[0].section_type == ChunkSectionType.QUESTION
    assert first[-1].section_type == ChunkSectionType.ACCEPTED_ANSWER
    assert first[-1].answer_external_id == "42"


def test_code_block_stays_atomic_when_it_fits_and_preserves_indentation() -> None:
    code = "```python\ndef work(value):\n    if value:\n        return value + 1\n```"
    chunks = chunker().chunk(
        canonical(CanonicalSection(ChunkSectionType.ANSWER, "Ответ", code, "7"))
    )
    assert len(chunks) == 1
    assert chunks[0].has_code is True
    assert chunks[0].language == "python"
    assert "    if value:" in chunks[0].text
    assert "        return value + 1" in chunks[0].text


def test_oversized_code_is_split_by_lines_without_empty_chunks() -> None:
    lines = [f"    value_{index} = source_{index} + 1" for index in range(30)]
    code = "```python\n" + "\n".join(lines) + "\n```"
    chunks = chunker().chunk(
        canonical(CanonicalSection(ChunkSectionType.ANSWER, "Ответ", code, "8"))
    )
    assert len(chunks) > 1
    assert all(item.has_code and item.text.strip() for item in chunks)
    assert all(item.token_count <= 28 for item in chunks)
    assert all("    value_" in item.text for item in chunks)


def test_text_overlap_and_stable_keys() -> None:
    text = "\n\n".join(
        [
            "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu",
            "nu xi omicron pi rho sigma tau upsilon phi chi psi omega",
            "one two three four five six seven eight nine ten eleven twelve",
        ]
    )
    chunks = chunker().chunk(canonical(CanonicalSection(ChunkSectionType.QUESTION, "Вопрос", text)))
    assert len(chunks) >= 2
    previous_tail = set(chunks[0].text.split()[-4:])
    assert previous_tail.intersection(chunks[1].text.split()[:6])

    document_id = UUID("00000000-0000-0000-0000-000000000123")
    first = stable_chunk_key(document_id, 2, 0, chunks[0].content_hash)
    assert first == stable_chunk_key(document_id, 2, 0, chunks[0].content_hash)
    assert first != stable_chunk_key(document_id, 3, 0, chunks[0].content_hash)
    assert len(first) == 64
