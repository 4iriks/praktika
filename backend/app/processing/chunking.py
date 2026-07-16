from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from uuid import UUID

from app.core.enums import ChunkSectionType
from app.processing.canonical import CanonicalDocument, CanonicalSection

TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)
FENCE_OPEN_PATTERN = re.compile(r"^(`{3,})([a-zA-Z0-9_+#.-]*)\n")


class TokenCounter:
    def count(self, value: str) -> int:
        raise NotImplementedError

    def split(self, value: str, maximum_tokens: int) -> list[str]:
        raise NotImplementedError

    def tail(self, value: str, maximum_tokens: int) -> str:
        raise NotImplementedError


class ApproximateTokenCounter(TokenCounter):
    def count(self, value: str) -> int:
        return len(TOKEN_PATTERN.findall(value))

    def split(self, value: str, maximum_tokens: int) -> list[str]:
        if maximum_tokens <= 0:
            raise ValueError("maximum_tokens должен быть положительным")
        matches = list(TOKEN_PATTERN.finditer(value))
        if not matches:
            return []
        parts: list[str] = []
        start = 0
        for offset in range(maximum_tokens, len(matches), maximum_tokens):
            end = matches[offset - 1].end()
            parts.append(value[start:end].strip())
            start = matches[offset].start()
        tail = value[start:].strip()
        if tail:
            parts.append(tail)
        return parts

    def tail(self, value: str, maximum_tokens: int) -> str:
        if maximum_tokens <= 0:
            return ""
        matches = list(TOKEN_PATTERN.finditer(value))
        if len(matches) <= maximum_tokens:
            return value.strip()
        return value[matches[-maximum_tokens].start() :].strip()


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    ordinal: int
    section_type: ChunkSectionType
    answer_external_id: str | None
    text: str
    contextual_text: str
    content_hash: str
    token_count: int
    character_count: int
    has_code: bool
    language: str | None


@dataclass(frozen=True, slots=True)
class ChunkingSettings:
    target_tokens: int = 650
    max_tokens: int = 900
    overlap_tokens: int = 80
    min_tokens: int = 40

    def __post_init__(self) -> None:
        if not 1 <= self.min_tokens <= self.target_tokens <= self.max_tokens:
            raise ValueError("Некорректные границы размера chunk")
        if not 0 <= self.overlap_tokens < self.target_tokens:
            raise ValueError("Некорректный overlap chunk")


@dataclass(frozen=True, slots=True)
class _AtomicBlock:
    text: str
    has_code: bool
    language: str | None


class DocumentChunker:
    def __init__(
        self,
        settings: ChunkingSettings,
        *,
        token_counter: TokenCounter | None = None,
    ) -> None:
        self._settings = settings
        self._tokens = token_counter or ApproximateTokenCounter()

    def chunk(self, document: CanonicalDocument) -> list[ChunkDraft]:
        raw_chunks: list[tuple[CanonicalSection, str, bool, str | None]] = []
        for section in document.sections:
            section_chunks = self._chunk_section(section)
            for text, has_code, language in section_chunks:
                raw_chunks.append((section, text, has_code, language))

        drafts: list[ChunkDraft] = []
        for section, text, has_code, language in raw_chunks:
            normalized = text.strip()
            if not normalized:
                continue
            token_count = self._tokens.count(normalized)
            if token_count > self._settings.max_tokens:
                raise ValueError("Chunk превысил максимальное число токенов")
            context = (
                f"# {document.title}\n"
                f"Теги: {', '.join(document.tags)}\n"
                f"Раздел: {section.label}\n\n{normalized}"
            )
            drafts.append(
                ChunkDraft(
                    ordinal=len(drafts),
                    section_type=section.section_type,
                    answer_external_id=section.answer_external_id,
                    text=normalized,
                    contextual_text=context,
                    content_hash=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
                    token_count=token_count,
                    character_count=len(normalized),
                    has_code=has_code,
                    language=language,
                )
            )
        return drafts

    def _chunk_section(self, section: CanonicalSection) -> list[tuple[str, bool, str | None]]:
        blocks: list[_AtomicBlock] = []
        for block in _markdown_blocks(section.text):
            blocks.extend(self._split_oversized(block))
        packed: list[tuple[str, bool, str | None]] = []
        current: list[_AtomicBlock] = []
        previous_text = ""

        def flush() -> None:
            nonlocal current, previous_text
            if not current:
                return
            combined = "\n\n".join(item.text for item in current).strip()
            has_code = any(item.has_code for item in current)
            languages = {item.language for item in current if item.language}
            language = next(iter(languages)) if len(languages) == 1 else None
            if (
                packed
                and self._tokens.count(combined) < self._settings.min_tokens
                and self._tokens.count(packed[-1][0] + "\n\n" + combined)
                <= self._settings.max_tokens
            ):
                prior_text, prior_code, prior_language = packed.pop()
                merged_language = prior_language if prior_language == language else None
                combined = prior_text + "\n\n" + combined
                has_code = prior_code or has_code
                language = merged_language
            elif packed and not has_code and self._settings.overlap_tokens and previous_text:
                overlap = self._tokens.tail(previous_text, self._settings.overlap_tokens)
                candidate = f"{overlap}\n\n{combined}" if overlap else combined
                if self._tokens.count(candidate) <= self._settings.max_tokens:
                    combined = candidate
            packed.append((combined, has_code, language))
            previous_text = combined
            current = []

        for block in blocks:
            candidate = "\n\n".join([*(item.text for item in current), block.text])
            if current and self._tokens.count(candidate) > self._settings.target_tokens:
                flush()
            current.append(block)
            current_size = self._tokens.count("\n\n".join(item.text for item in current))
            if current_size >= self._settings.target_tokens:
                flush()
        flush()
        return packed

    def _split_oversized(self, block: _AtomicBlock) -> list[_AtomicBlock]:
        if self._tokens.count(block.text) <= self._settings.max_tokens:
            return [block]
        if not block.has_code:
            return [
                _AtomicBlock(part, False, None)
                for part in self._tokens.split(block.text, self._settings.max_tokens)
            ]
        return _split_code_block(block, self._tokens, self._settings.max_tokens)


def stable_chunk_key(
    document_id: UUID,
    document_version: int,
    ordinal: int,
    content_hash: str,
) -> str:
    value = f"{document_id}:{document_version}:{ordinal}:{content_hash}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _markdown_blocks(value: str) -> list[_AtomicBlock]:
    lines = value.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    blocks: list[_AtomicBlock] = []
    text_lines: list[str] = []
    index = 0

    def flush_text() -> None:
        nonlocal text_lines
        text = "\n".join(text_lines).strip()
        if text:
            blocks.append(_AtomicBlock(text, False, None))
        text_lines = []

    while index < len(lines):
        line = lines[index]
        match = re.match(r"^(`{3,})([a-zA-Z0-9_+#.-]*)$", line.strip())
        if match:
            flush_text()
            fence = match.group(1)
            language = match.group(2).casefold() or None
            code_lines = [line]
            index += 1
            while index < len(lines):
                code_lines.append(lines[index])
                if lines[index].strip() == fence:
                    index += 1
                    break
                index += 1
            blocks.append(_AtomicBlock("\n".join(code_lines), True, language))
            continue
        if not line.strip():
            flush_text()
        else:
            text_lines.append(line)
        index += 1
    flush_text()
    return blocks


def _split_code_block(
    block: _AtomicBlock,
    counter: TokenCounter,
    maximum_tokens: int,
) -> list[_AtomicBlock]:
    match = FENCE_OPEN_PATTERN.match(block.text)
    if match is None:
        return [
            _AtomicBlock(part, True, block.language)
            for part in counter.split(block.text, maximum_tokens)
        ]
    fence = match.group(1)
    language = match.group(2)
    body = block.text[match.end() :]
    if body.endswith("\n" + fence):
        body = body[: -(len(fence) + 1)]
    overhead = counter.count(f"{fence}{language}\n\n{fence}")
    capacity = max(1, maximum_tokens - overhead)
    groups: list[list[str]] = []
    current: list[str] = []
    for line in body.splitlines():
        candidate = "\n".join([*current, line])
        if current and counter.count(candidate) > capacity:
            groups.append(current)
            current = []
        if counter.count(line) > capacity:
            if current:
                groups.append(current)
                current = []
            groups.extend([[part] for part in counter.split(line, capacity)])
        else:
            current.append(line)
    if current:
        groups.append(current)
    return [
        _AtomicBlock(
            f"{fence}{language}\n{'\n'.join(group)}\n{fence}",
            True,
            block.language,
        )
        for group in groups
        if group
    ]
