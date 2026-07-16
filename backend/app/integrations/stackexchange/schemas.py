from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field


class StackExchangeModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class StackExchangeOwner(StackExchangeModel):
    user_id: int | None = None
    display_name: str = ""
    link: str | None = None


class StackExchangeQuestion(StackExchangeModel):
    question_id: int
    title: str = ""
    body: str = ""
    tags: list[str] = Field(default_factory=list)
    link: str = ""
    owner: StackExchangeOwner | None = None
    creation_date: int
    last_activity_date: int
    last_edit_date: int | None = None
    score: int = 0
    view_count: int = 0
    answer_count: int = 0
    accepted_answer_id: int | None = None
    is_answered: bool = False
    content_license: str | None = None


class StackExchangeAnswer(StackExchangeModel):
    answer_id: int
    question_id: int
    body: str = ""
    owner: StackExchangeOwner | None = None
    creation_date: int
    last_activity_date: int
    last_edit_date: int | None = None
    score: int = 0
    is_accepted: bool = False
    content_license: str | None = None


ItemT = TypeVar("ItemT")


class StackExchangeEnvelope[ItemT](StackExchangeModel):
    items: list[ItemT] = Field(default_factory=list)
    has_more: bool = False
    quota_max: int | None = None
    quota_remaining: int | None = None
    backoff: int | None = Field(default=None, ge=0)
    error_id: int | None = None
    error_name: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class StackExchangePage[ItemT]:
    page: int
    envelope: StackExchangeEnvelope[ItemT]
    response_bytes: int


@dataclass(frozen=True, slots=True)
class StackExchangeResponseMetrics:
    method: str
    page: int
    response_bytes: int
    quota_remaining: int | None
    quota_max: int | None
