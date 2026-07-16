from __future__ import annotations

import re
from dataclasses import dataclass

_CITATION = re.compile(r"\[(\d{1,4})\]")


@dataclass(frozen=True, slots=True)
class CitationValidation:
    answer: str
    valid: bool
    cited_indexes: tuple[int, ...]
    invalid_indexes: tuple[int, ...]


def validate_citations(answer: str, allowed_count: int) -> CitationValidation:
    cited: set[int] = set()
    invalid: set[int] = set()

    def replace(match: re.Match[str]) -> str:
        index = int(match.group(1))
        if 1 <= index <= allowed_count:
            cited.add(index)
            return match.group(0)
        invalid.add(index)
        return ""

    cleaned = _CITATION.sub(replace, answer)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned).strip()
    return CitationValidation(
        answer=cleaned,
        valid=not invalid,
        cited_indexes=tuple(sorted(cited)),
        invalid_indexes=tuple(sorted(invalid)),
    )
