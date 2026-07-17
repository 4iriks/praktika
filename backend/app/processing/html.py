from __future__ import annotations

import html
import re
import unicodedata
import warnings
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning
from bs4.element import Comment, NavigableString, Tag

BlockKind = Literal["heading", "paragraph", "list", "quote", "code"]
ALLOWED_TAGS = frozenset(
    {
        "a",
        "b",
        "blockquote",
        "br",
        "code",
        "em",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "i",
        "li",
        "ol",
        "p",
        "pre",
        "strong",
        "ul",
    }
)
DANGEROUS_TAGS = frozenset({"script", "style", "iframe", "object", "embed", "svg", "math"})
LANGUAGE_PATTERN = re.compile(r"^(?:language-|lang-)([a-zA-Z0-9_+#.-]{1,30})$")
WHITESPACE_PATTERN = re.compile(r"[\t \f\v\u00a0]+")
BLANK_LINES_PATTERN = re.compile(r"\n{3,}")
BACKTICK_RUN_PATTERN = re.compile(r"`+")


class HtmlContentError(ValueError):
    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


@dataclass(frozen=True, slots=True)
class ContentBlock:
    kind: BlockKind
    text: str
    language: str | None = None


@dataclass(frozen=True, slots=True)
class CleanedContent:
    text: str
    sanitized_html: str
    blocks: tuple[ContentBlock, ...]
    has_code: bool


def clean_title(value: str, *, maximum_characters: int = 500) -> str:
    decoded = html.unescape(value.replace("\r\n", "\n").replace("\r", "\n"))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", MarkupResemblesLocatorWarning)
        plain = BeautifulSoup(decoded, "lxml").get_text(" ", strip=True)
    normalized = _normalize_text_block(unicodedata.normalize("NFC", plain))
    return normalized[:maximum_characters].strip()


def clean_html(
    value: str,
    *,
    maximum_input_bytes: int,
    maximum_output_characters: int,
) -> CleanedContent:
    if len(value.encode("utf-8")) > maximum_input_bytes:
        raise HtmlContentError("HTML_TOO_LARGE", "HTML публикации превысил допустимый размер")
    normalized_input = unicodedata.normalize(
        "NFC",
        value.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", ""),
    )
    soup = BeautifulSoup(normalized_input, "lxml")
    for comment in soup.find_all(string=lambda item: isinstance(item, Comment)):
        comment.extract()
    for tag in list(soup.find_all(DANGEROUS_TAGS)):
        tag.decompose()
    _sanitize_tree(soup)
    container = soup.body or soup
    blocks = tuple(_extract_blocks(container))
    text = BLANK_LINES_PATTERN.sub("\n\n", "\n\n".join(block.text for block in blocks)).strip()
    if len(text) > maximum_output_characters:
        raise HtmlContentError(
            "CLEANED_CONTENT_TOO_LARGE",
            "Очищенный текст публикации превысил допустимый размер",
        )
    sanitized_html = "".join(str(child) for child in container.children).strip()
    return CleanedContent(
        text=text,
        sanitized_html=sanitized_html,
        blocks=blocks,
        has_code=any(block.kind == "code" for block in blocks),
    )


def _sanitize_tree(soup: BeautifulSoup) -> None:
    for tag in list(soup.find_all(True)):
        name = tag.name.casefold()
        if name in {"html", "body"}:
            tag.attrs = {}
            continue
        if name not in ALLOWED_TAGS:
            tag.unwrap()
            continue
        if name == "a":
            href = str(tag.attrs.get("href", "")).strip()
            tag.attrs = {}
            if _safe_http_url(href):
                tag["href"] = href
        elif name == "code":
            language = _detect_language(tag)
            tag.attrs = {}
            if language:
                tag["class"] = f"language-{language}"
        else:
            tag.attrs = {}


def _safe_http_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return parsed.scheme.casefold() in {"http", "https"} and bool(parsed.netloc)


def _extract_blocks(container: Tag | BeautifulSoup) -> Iterable[ContentBlock]:
    emitted = False
    for child in container.children:
        if isinstance(child, NavigableString):
            text = _normalize_text_block(str(child))
            if text:
                emitted = True
                yield ContentBlock("paragraph", text)
            continue
        if not isinstance(child, Tag):
            continue
        name = child.name.casefold()
        if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            text = _normalize_text_block(_render_inline(child))
            if text:
                emitted = True
                level = min(6, max(1, int(name[1])))
                yield ContentBlock("heading", f"{'#' * level} {text}")
        elif name == "pre":
            code = _normalize_code(child.get_text("", strip=False))
            if code:
                emitted = True
                language = _detect_language(child)
                fence = _code_fence(code)
                yield ContentBlock("code", f"{fence}{language or ''}\n{code}\n{fence}", language)
        elif name in {"ul", "ol"}:
            items: list[str] = []
            for index, item in enumerate(child.find_all("li", recursive=False), start=1):
                text = _normalize_text_block(_render_inline(item))
                if text:
                    prefix = f"{index}." if name == "ol" else "-"
                    items.append(f"{prefix} {text}")
            if items:
                emitted = True
                yield ContentBlock("list", "\n".join(items))
        elif name == "blockquote":
            text = _normalize_text_block(_render_inline(child))
            if text:
                emitted = True
                yield ContentBlock("quote", "\n".join(f"> {line}" for line in text.splitlines()))
        elif name in {"p", "li"}:
            text = _normalize_text_block(_render_inline(child))
            if text:
                emitted = True
                yield ContentBlock("paragraph", text)
        else:
            nested = tuple(_extract_blocks(child))
            if nested:
                emitted = True
                yield from nested
    if not emitted:
        fallback = _normalize_text_block(container.get_text(" ", strip=True))
        if fallback:
            yield ContentBlock("paragraph", fallback)


def _render_inline(node: Tag) -> str:
    parts: list[str] = []
    for child in node.children:
        if isinstance(child, NavigableString):
            parts.append(str(child))
        elif isinstance(child, Tag):
            name = child.name.casefold()
            if name == "br":
                parts.append("\n")
            elif name == "code" and child.parent and child.parent.name != "pre":
                code = unicodedata.normalize("NFC", child.get_text("", strip=False))
                delimiter = "``" if "`" in code else "`"
                parts.append(f"{delimiter}{code}{delimiter}")
            elif name == "a":
                label = _render_inline(child).strip() or child.get_text(" ", strip=True)
                href = str(child.attrs.get("href", ""))
                parts.append(f"[{label}]({href})" if href else label)
            else:
                parts.append(_render_inline(child))
    return "".join(parts)


def _detect_language(tag: Tag) -> str | None:
    candidates: list[str] = []
    current: Tag | None = tag
    for _ in range(2):
        if current is None:
            break
        raw_classes: object = current.attrs.get("class", [])
        if isinstance(raw_classes, str):
            candidates.extend(raw_classes.split())
        elif isinstance(raw_classes, list):
            candidates.extend(str(item) for item in raw_classes)
        current = current.find("code", recursive=False) if current.name == "pre" else None
    for candidate in candidates:
        match = LANGUAGE_PATTERN.fullmatch(candidate)
        if match:
            return match.group(1).casefold()
    return None


def _normalize_text_block(value: str) -> str:
    lines = [WHITESPACE_PATTERN.sub(" ", line).strip() for line in value.splitlines()]
    return BLANK_LINES_PATTERN.sub("\n\n", "\n".join(lines)).strip()


def _normalize_code(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
    return normalized.strip("\n")


def _code_fence(code: str) -> str:
    longest = max((len(match.group()) for match in BACKTICK_RUN_PATTERN.finditer(code)), default=0)
    return "`" * max(3, longest + 1)
