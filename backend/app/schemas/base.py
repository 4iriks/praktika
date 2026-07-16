from __future__ import annotations

import re
from typing import TypeVar

from pydantic import BaseModel, ConfigDict


def to_camel(value: str) -> str:
    return re.sub(r"_([a-z])", lambda match: match.group(1).upper(), value)


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
    )


class Pagination(ApiModel):
    page: int
    page_size: int
    total: int
    total_pages: int


T = TypeVar("T")


def pagination(page: int, page_size: int, total: int) -> Pagination:
    pages = max(1, (total + page_size - 1) // page_size)
    return Pagination(page=page, page_size=page_size, total=total, total_pages=pages)
