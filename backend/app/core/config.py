from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
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
    app_version: str = Field(default="0.6.0", alias="APP_VERSION")
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
    stackexchange_api_base_url: str = Field(
        default="https://api.stackexchange.com/2.3", alias="STACKEXCHANGE_API_BASE_URL"
    )
    stackexchange_key: SecretStr | None = Field(
        default=None,
        alias="STACKEXCHANGE_KEY",
        repr=False,
    )
    stackexchange_question_filter: str = Field(
        default="withbody", alias="STACKEXCHANGE_QUESTION_FILTER"
    )
    stackexchange_answer_filter: str = Field(
        default="withbody", alias="STACKEXCHANGE_ANSWER_FILTER"
    )
    stackexchange_page_size: int = Field(default=100, ge=1, le=100, alias="STACKEXCHANGE_PAGE_SIZE")
    stackexchange_requests_per_second: float = Field(
        default=3, gt=0, le=10, alias="STACKEXCHANGE_REQUESTS_PER_SECOND"
    )
    stackexchange_connect_timeout_seconds: float = Field(
        default=5, gt=0, le=60, alias="STACKEXCHANGE_CONNECT_TIMEOUT_SECONDS"
    )
    stackexchange_read_timeout_seconds: float = Field(
        default=20, gt=0, le=120, alias="STACKEXCHANGE_READ_TIMEOUT_SECONDS"
    )
    stackexchange_write_timeout_seconds: float = Field(
        default=10, gt=0, le=60, alias="STACKEXCHANGE_WRITE_TIMEOUT_SECONDS"
    )
    stackexchange_pool_timeout_seconds: float = Field(
        default=5, gt=0, le=60, alias="STACKEXCHANGE_POOL_TIMEOUT_SECONDS"
    )
    stackexchange_max_retries: int = Field(
        default=4, ge=0, le=10, alias="STACKEXCHANGE_MAX_RETRIES"
    )
    stackexchange_quota_reserve: int = Field(
        default=100, ge=0, le=10000, alias="STACKEXCHANGE_QUOTA_RESERVE"
    )
    stackexchange_max_response_bytes: int = Field(
        default=8_000_000,
        ge=1024,
        le=50_000_000,
        alias="STACKEXCHANGE_MAX_RESPONSE_BYTES",
    )
    stackexchange_max_pages: int = Field(
        default=1000, ge=1, le=10000, alias="STACKEXCHANGE_MAX_PAGES"
    )
    stackexchange_incremental_overlap_seconds: int = Field(
        default=86400,
        ge=0,
        le=604800,
        alias="STACKEXCHANGE_INCREMENTAL_OVERLAP_SECONDS",
    )
    stackexchange_user_agent: str = Field(
        default="PyAnswer/0.5 StackExchange ingestion worker",
        min_length=8,
        max_length=200,
        alias="STACKEXCHANGE_USER_AGENT",
    )

    worker_poll_interval_seconds: float = Field(
        default=2, gt=0, le=60, alias="WORKER_POLL_INTERVAL_SECONDS"
    )
    worker_lease_seconds: int = Field(default=60, ge=15, le=3600, alias="WORKER_LEASE_SECONDS")
    worker_heartbeat_seconds: int = Field(
        default=15, ge=1, le=300, alias="WORKER_HEARTBEAT_SECONDS"
    )
    worker_max_attempts: int = Field(default=5, ge=1, le=20, alias="WORKER_MAX_ATTEMPTS")
    worker_shutdown_timeout_seconds: int = Field(
        default=30, ge=1, le=300, alias="WORKER_SHUTDOWN_TIMEOUT_SECONDS"
    )

    qdrant_url: str = Field(default="http://localhost:6333", alias="QDRANT_URL")
    qdrant_server_version: str = Field(default="1.18.2", alias="QDRANT_SERVER_VERSION")
    qdrant_client_version: str = Field(default="1.18.0", alias="QDRANT_CLIENT_VERSION")
    qdrant_alias: str = Field(default="pyanswer_chunks_current", alias="QDRANT_ALIAS")
    qdrant_collection_prefix: str = Field(
        default="pyanswer_chunks", alias="QDRANT_COLLECTION_PREFIX"
    )
    qdrant_timeout_seconds: float = Field(default=30, gt=0, le=300, alias="QDRANT_TIMEOUT_SECONDS")
    qdrant_max_retries: int = Field(default=3, ge=0, le=10, alias="QDRANT_MAX_RETRIES")

    embedding_provider: Literal["ollama"] = Field(default="ollama", alias="EMBEDDING_PROVIDER")
    embedding_model: str = Field(default="qwen3-embedding:0.6b", alias="EMBEDDING_MODEL")
    embedding_dimensions: int = Field(default=1024, ge=1, alias="EMBEDDING_DIMENSIONS")
    embedding_batch_size: int = Field(default=16, ge=1, le=128, alias="EMBEDDING_BATCH_SIZE")
    embedding_timeout_seconds: float = Field(
        default=120, gt=0, le=900, alias="EMBEDDING_TIMEOUT_SECONDS"
    )
    embedding_max_retries: int = Field(default=3, ge=0, le=10, alias="EMBEDDING_MAX_RETRIES")
    embedding_keep_alive: str = Field(default="5m", alias="EMBEDDING_KEEP_ALIVE")
    embedding_max_input_tokens: int = Field(
        default=8192, ge=128, le=65536, alias="EMBEDDING_MAX_INPUT_TOKENS"
    )
    embedding_query_instruction: str = Field(
        default=(
            "Instruct: Given a Russian Python programming question, retrieve passages that "
            "directly help answer the query\nQuery: {query}"
        ),
        alias="EMBEDDING_QUERY_INSTRUCTION",
    )
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")

    sparse_provider: Literal["qdrant_bm25", "fastembed_bm25"] = Field(
        default="qdrant_bm25", alias="SPARSE_PROVIDER"
    )
    sparse_model: str = Field(default="qdrant/bm25", alias="SPARSE_MODEL")

    index_schema_version: str = Field(default="6.1", alias="INDEX_SCHEMA_VERSION")
    index_chunk_schema_version: str = Field(default="5.2", alias="INDEX_CHUNK_SCHEMA_VERSION")
    index_payload_schema_version: str = Field(default="6.1", alias="INDEX_PAYLOAD_SCHEMA_VERSION")
    index_embed_batch_size: int = Field(default=16, ge=1, le=128, alias="INDEX_EMBED_BATCH_SIZE")
    index_qdrant_upsert_batch_size: int = Field(
        default=64, ge=1, le=512, alias="INDEX_QDRANT_UPSERT_BATCH_SIZE"
    )
    index_max_concurrent_embed_requests: int = Field(
        default=1, ge=1, le=8, alias="INDEX_MAX_CONCURRENT_EMBED_REQUESTS"
    )
    index_max_concurrent_qdrant_requests: int = Field(
        default=1, ge=1, le=8, alias="INDEX_MAX_CONCURRENT_QDRANT_REQUESTS"
    )
    index_job_max_attempts: int = Field(default=5, ge=1, le=20, alias="INDEX_JOB_MAX_ATTEMPTS")
    index_request_timeout_seconds: float = Field(
        default=120, gt=0, le=900, alias="INDEX_REQUEST_TIMEOUT_SECONDS"
    )
    index_hnsw_m: int = Field(default=16, ge=4, le=128, alias="INDEX_HNSW_M")
    index_hnsw_ef_construct: int = Field(
        default=100, ge=16, le=1024, alias="INDEX_HNSW_EF_CONSTRUCT"
    )
    index_retain_retired_count: int = Field(
        default=1, ge=0, le=10, alias="INDEX_RETAIN_RETIRED_COUNT"
    )
    index_failed_collection_retention_hours: int = Field(
        default=24, ge=1, le=720, alias="INDEX_FAILED_COLLECTION_RETENTION_HOURS"
    )
    index_auto_cleanup: bool = Field(default=False, alias="INDEX_AUTO_CLEANUP")
    index_allow_possible_duplicates: bool = Field(
        default=False, alias="INDEX_ALLOW_POSSIBLE_DUPLICATES"
    )
    auto_enqueue_document_reindex: bool = Field(default=True, alias="AUTO_ENQUEUE_DOCUMENT_REINDEX")

    document_revision_limit: int = Field(default=10, ge=1, le=100, alias="DOCUMENT_REVISION_LIMIT")
    chunk_target_tokens: int = Field(default=650, ge=50, le=4000, alias="CHUNK_TARGET_TOKENS")
    chunk_max_tokens: int = Field(default=900, ge=100, le=6000, alias="CHUNK_MAX_TOKENS")
    chunk_overlap_tokens: int = Field(default=80, ge=0, le=500, alias="CHUNK_OVERLAP_TOKENS")
    chunk_min_tokens: int = Field(default=40, ge=1, le=500, alias="CHUNK_MIN_TOKENS")
    min_question_text_length: int = Field(
        default=20, ge=1, le=1000, alias="MIN_QUESTION_TEXT_LENGTH"
    )
    min_answer_text_length: int = Field(default=1, ge=1, le=1000, alias="MIN_ANSWER_TEXT_LENGTH")
    max_document_text_length: int = Field(
        default=500_000, ge=1000, le=2_000_000, alias="MAX_DOCUMENT_TEXT_LENGTH"
    )
    max_answer_count_per_question: int = Field(
        default=500, ge=1, le=5000, alias="MAX_ANSWER_COUNT_PER_QUESTION"
    )
    max_html_body_bytes: int = Field(
        default=2_000_000, ge=1024, le=10_000_000, alias="MAX_HTML_BODY_BYTES"
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
        if self.worker_heartbeat_seconds >= self.worker_lease_seconds:
            raise ValueError("WORKER_HEARTBEAT_SECONDS должен быть меньше WORKER_LEASE_SECONDS")
        if self.stackexchange_api_base_url.rstrip("/") != "https://api.stackexchange.com/2.3":
            raise ValueError(
                "STACKEXCHANGE_API_BASE_URL должен указывать на Stack Exchange API 2.3"
            )
        if self.chunk_target_tokens > self.chunk_max_tokens:
            raise ValueError("CHUNK_TARGET_TOKENS не может превышать CHUNK_MAX_TOKENS")
        if self.chunk_overlap_tokens >= self.chunk_target_tokens:
            raise ValueError("CHUNK_OVERLAP_TOKENS должен быть меньше CHUNK_TARGET_TOKENS")
        if self.chunk_min_tokens > self.chunk_target_tokens:
            raise ValueError("CHUNK_MIN_TOKENS не может превышать CHUNK_TARGET_TOKENS")
        if self.embedding_batch_size > self.index_qdrant_upsert_batch_size:
            raise ValueError(
                "EMBEDDING_BATCH_SIZE не может превышать INDEX_QDRANT_UPSERT_BATCH_SIZE"
            )
        if "{query}" not in self.embedding_query_instruction:
            raise ValueError("EMBEDDING_QUERY_INSTRUCTION должен содержать {query}")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
