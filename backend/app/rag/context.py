from __future__ import annotations

import hashlib
import re
from collections import OrderedDict
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RetrievedPassage:
    chunk_id: UUID
    document_id: UUID
    title: str
    source_url: str
    tags: tuple[str, ...]
    section_type: str
    text: str
    rank: int
    bm25_score: float | None
    vector_score: float | None
    fusion_score: float
    reranker_score: float | None
    final_score: float
    saved: bool


@dataclass(frozen=True, slots=True)
class ContextSource:
    citation_index: int
    chunk_id: UUID
    document_id: UUID
    title: str
    source_url: str
    tags: tuple[str, ...]
    section_type: str
    passage: str
    rank: int
    bm25_score: float | None
    vector_score: float | None
    fusion_score: float
    reranker_score: float | None
    final_score: float
    saved: bool

    @property
    def passage_hash(self) -> str:
        return hashlib.sha256(self.passage.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class BuiltContext:
    text: str
    sources: tuple[ContextSource, ...]
    token_count: int


class ContextBuilder:
    def __init__(
        self,
        *,
        token_budget: int,
        max_sources: int,
        max_chunks_per_document: int,
    ) -> None:
        self._token_budget = token_budget
        self._max_sources = max_sources
        self._max_chunks_per_document = max_chunks_per_document

    def build(self, passages: list[RetrievedPassage]) -> BuiltContext:
        grouped: OrderedDict[UUID, list[RetrievedPassage]] = OrderedDict()
        seen: list[str] = []
        for passage in sorted(passages, key=lambda item: (item.rank, str(item.chunk_id))):
            normalized = _dedup_text(passage.text)
            if not normalized or any(_overlaps(normalized, previous) for previous in seen):
                continue
            group = grouped.setdefault(passage.document_id, [])
            if len(group) >= self._max_chunks_per_document:
                continue
            group.append(passage)
            seen.append(normalized)
        sources: list[ContextSource] = []
        blocks: list[str] = []
        used_tokens = 0
        for group in grouped.values():
            if len(sources) >= self._max_sources:
                break
            best = group[0]
            passage_text = "\n\n".join(item.text.strip() for item in group if item.text.strip())
            safe_passage = _escape_source_citations(passage_text)
            citation = len(sources) + 1
            block = _source_block(citation, best, safe_passage)
            tokens = _tokens(block)
            if used_tokens + tokens > self._token_budget:
                remaining = self._token_budget - used_tokens
                if remaining < 40:
                    continue
                safe_passage = _truncate(safe_passage, remaining * 4)
                block = _source_block(citation, best, safe_passage)
                tokens = _tokens(block)
            sources.append(
                ContextSource(
                    citation_index=citation,
                    chunk_id=best.chunk_id,
                    document_id=best.document_id,
                    title=best.title,
                    source_url=best.source_url,
                    tags=best.tags,
                    section_type=best.section_type,
                    passage=safe_passage,
                    rank=best.rank,
                    bm25_score=best.bm25_score,
                    vector_score=best.vector_score,
                    fusion_score=best.fusion_score,
                    reranker_score=best.reranker_score,
                    final_score=best.final_score,
                    saved=best.saved,
                )
            )
            blocks.append(block)
            used_tokens += tokens
        return BuiltContext(
            text="\n\n".join(blocks), sources=tuple(sources), token_count=used_tokens
        )


def _source_block(index: int, passage: RetrievedPassage, text: str) -> str:
    tags = ", ".join(passage.tags)
    return (
        f'<source id="{index}">\n'
        f"Цитата: [{index}]\n"
        f"Заголовок: {passage.title}\n"
        f"Теги: {tags}\n"
        f"Раздел: {passage.section_type}\n"
        "<<<SOURCE_DATA>>>\n"
        f"{text}\n"
        "<<<END_SOURCE_DATA>>>\n"
        "</source>"
    )


def _escape_source_citations(text: str) -> str:
    return re.sub(r"\[(\d{1,4})\]", r"〔\1〕", text)


def _dedup_text(text: str) -> str:
    return " ".join(text.casefold().split())


def _overlaps(value: str, previous: str) -> bool:
    if value == previous:
        return True
    shorter, longer = sorted((value, previous), key=len)
    return len(shorter) >= 80 and shorter in longer


def _truncate(text: str, max_characters: int) -> str:
    if len(text) <= max_characters:
        return text
    boundary = text.rfind("\n", 0, max_characters)
    cut = boundary if boundary >= max_characters // 2 else max_characters
    return text[:cut].rstrip() + "\n… [фрагмент сокращён]"


def _tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)
