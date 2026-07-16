from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = Field(
        default="development", alias="APP_ENV"
    )
    app_name: str = Field(default="PyAnswer API", alias="APP_NAME")
    app_version: str = Field(default="0.4.0", alias="APP_VERSION")
    debug: bool = Field(default=False, alias="DEBUG")
    database_url: str = Field(
        default="postgresql+asyncpg://pyanswer:pyanswer@localhost:5432/pyanswer",
        alias="DATABASE_URL",
    )
    test_database_url: str | None = Field(default=None, alias="TEST_DATABASE_URL")
    frontend_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173"], alias="FRONTEND_ORIGINS"
    )

    session_cookie_name: str = Field(default="pyanswer_session", alias="SESSION_COOKIE_NAME")
    csrf_cookie_name: str = Field(default="pyanswer_csrf", alias="CSRF_COOKIE_NAME")
    session_ttl_hours: int = Field(default=12, ge=1, le=168, alias="SESSION_TTL_HOURS")
    remember_session_ttl_days: int = Field(
        default=30, ge=1, le=365, alias="REMEMBER_SESSION_TTL_DAYS"
    )
    cookie_secure: bool = Field(default=False, alias="COOKIE_SECURE")
    cookie_samesite: Literal["lax", "strict", "none"] = Field(
        default="lax", alias="COOKIE_SAMESITE"
    )

    argon2_time_cost: int = Field(default=3, ge=1, le=10, alias="ARGON2_TIME_COST")
    argon2_memory_cost: int = Field(default=65536, ge=8192, alias="ARGON2_MEMORY_COST")
    argon2_parallelism: int = Field(default=2, ge=1, le=8, alias="ARGON2_PARALLELISM")

    bootstrap_admin_email: str | None = Field(default=None, alias="BOOTSTRAP_ADMIN_EMAIL")
    bootstrap_admin_password: str | None = Field(default=None, alias="BOOTSTRAP_ADMIN_PASSWORD")
    bootstrap_admin_name: str = Field(default="Администратор", alias="BOOTSTRAP_ADMIN_NAME")
    seed_demo_data: bool = Field(default=False, alias="SEED_DEMO_DATA")

    stack_exchange_site: str = Field(default="ru.stackoverflow", alias="STACK_EXCHANGE_SITE")
    stack_exchange_tag: str = Field(default="python", alias="STACK_EXCHANGE_TAG")
    stack_exchange_target_documents: int = Field(
        default=25000, ge=5000, le=100000, alias="STACK_EXCHANGE_TARGET_DOCUMENTS"
    )

    auth_rate_limit_requests: int = Field(
        default=10, ge=1, le=1000, alias="AUTH_RATE_LIMIT_REQUESTS"
    )
    auth_rate_limit_window_seconds: int = Field(
        default=60, ge=1, le=3600, alias="AUTH_RATE_LIMIT_WINDOW_SECONDS"
    )
    docs_enabled: bool = Field(default=True, alias="DOCS_ENABLED")

    @model_validator(mode="after")
    def validate_production(self) -> Settings:
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError("COOKIE_SECURE=true обязателен для SameSite=None")
        if self.app_env == "production":
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE=true обязателен в production")
            if "pyanswer:pyanswer" in self.database_url:
                raise ValueError("DATABASE_URL должен быть задан явно в production")
            if self.seed_demo_data:
                raise ValueError("SEED_DEMO_DATA запрещён в production")
        if any(origin == "*" for origin in self.frontend_origins):
            raise ValueError("Wildcard CORS несовместим с cookie-auth")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
