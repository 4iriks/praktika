from __future__ import annotations

from datetime import datetime
from uuid import UUID

from email_validator import EmailNotValidError, validate_email
from pydantic import Field, field_validator

from app.core.enums import AccountStatus, Permission, SearchMode, SearchView, UserRole
from app.schemas.base import ApiModel


def validate_app_email(value: str) -> str:
    candidate = value.strip()
    local, separator, domain = candidate.rpartition("@")
    if separator and local and domain.casefold() == "pyanswer.local":
        return candidate
    try:
        return validate_email(candidate, check_deliverability=False).normalized
    except EmailNotValidError as exc:
        raise ValueError("Некорректный email") from exc


class UserPreferencesOut(ApiModel):
    default_search_mode: SearchMode
    default_search_view: SearchView
    default_page_size: int
    auto_open_scores: bool
    confirm_external_navigation: bool


class UserOut(ApiModel):
    id: UUID
    email: str
    display_name: str
    role: UserRole
    account_status: AccountStatus
    created_at: datetime
    last_active_at: datetime
    account_version: int
    preferences: UserPreferencesOut
    permissions: list[Permission] = Field(default_factory=list)


class RegisterRequest(ApiModel):
    display_name: str = Field(min_length=2, max_length=120)
    email: str
    password: str = Field(min_length=8, max_length=256)
    accepted_terms: bool
    remember: bool = False

    @field_validator("display_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 2:
            raise ValueError("Имя должно содержать минимум 2 символа")
        return stripped

    @field_validator("email")
    @classmethod
    def validate_email_address(cls, value: str) -> str:
        return validate_app_email(value)

    @field_validator("accepted_terms")
    @classmethod
    def require_terms(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Необходимо принять правила использования")
        return value


class LoginRequest(ApiModel):
    email: str
    password: str = Field(min_length=1, max_length=256)
    remember: bool = False

    @field_validator("email")
    @classmethod
    def validate_email_address(cls, value: str) -> str:
        return validate_app_email(value)


class UserPreferencesUpdate(ApiModel):
    default_search_mode: SearchMode
    default_search_view: SearchView
    default_page_size: int
    auto_open_scores: bool
    confirm_external_navigation: bool

    @field_validator("default_page_size")
    @classmethod
    def validate_page_size(cls, value: int) -> int:
        if value not in {10, 20, 50}:
            raise ValueError("Размер страницы должен быть 10, 20 или 50")
        return value


class UpdateProfileRequest(ApiModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=120)
    email: str | None = None
    preferences: UserPreferencesUpdate | None = None

    @field_validator("display_name")
    @classmethod
    def strip_optional_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("email")
    @classmethod
    def validate_optional_email(cls, value: str | None) -> str | None:
        return validate_app_email(value) if value is not None else None


class UserStatsOut(ApiModel):
    document_searches: int
    rag_searches: int
    saved_documents: int
    rated_answers: int


class CSRFResponse(ApiModel):
    csrf_token: str
