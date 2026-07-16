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
    app_version: str = Field(default="0.7.0", alias="APP_VERSION")
    debug: bool = Field(default=False, alias="DEBUG")
    database_url: str = Field(
        default="postgresql+asyncpg://pyanswer:pyanswer@localhost:5432/pyanswer",
        alias="DATABASE_URL",
    )
    test_database_url: str | None = Field(default=None, alias="TEST_DATABASE_URL")
    frontend_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:8080"], alias="FRONTEND_ORIGINS"
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
    embedding_document_max_input_tokens: int = Field(
        default=512,
        ge=16,
        le=8192,
        alias="EMBEDDING_DOCUMENT_MAX_INPUT_TOKENS",
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

    search_bm25_candidates: int = Field(default=60, ge=1, le=1000, alias="SEARCH_BM25_CANDIDATES")
    search_vector_candidates: int = Field(
        default=60, ge=1, le=1000, alias="SEARCH_VECTOR_CANDIDATES"
    )
    search_hybrid_candidates: int = Field(
        default=80, ge=1, le=1000, alias="SEARCH_HYBRID_CANDIDATES"
    )
    search_rrf_k: int = Field(default=60, ge=1, le=1000, alias="SEARCH_RRF_K")
    search_bm25_weight: float = Field(default=1.0, gt=0, le=10, alias="SEARCH_BM25_WEIGHT")
    search_vector_weight: float = Field(default=1.0, gt=0, le=10, alias="SEARCH_VECTOR_WEIGHT")
    search_max_limit: int = Field(default=50, ge=1, le=100, alias="SEARCH_MAX_LIMIT")
    search_max_candidates: int = Field(default=500, ge=10, le=5000, alias="SEARCH_MAX_CANDIDATES")
    search_timeout_seconds: float = Field(default=30, gt=0, le=300, alias="SEARCH_TIMEOUT_SECONDS")
    search_query_max_chars: int = Field(
        default=1000, ge=10, le=10000, alias="SEARCH_QUERY_MAX_CHARS"
    )
    search_query_max_tokens: int = Field(
        default=256, ge=4, le=2048, alias="SEARCH_QUERY_MAX_TOKENS"
    )
    search_max_chunks_per_document: int = Field(
        default=2, ge=1, le=10, alias="SEARCH_MAX_CHUNKS_PER_DOCUMENT"
    )
    search_group_by_document: bool = Field(default=True, alias="SEARCH_GROUP_BY_DOCUMENT")
    search_snippet_characters: int = Field(
        default=500, ge=100, le=2000, alias="SEARCH_SNIPPET_CHARACTERS"
    )
    search_embedding_concurrency: int = Field(
        default=2, ge=1, le=32, alias="SEARCH_EMBEDDING_CONCURRENCY"
    )
    search_embedding_queue_timeout_seconds: float = Field(
        default=5, gt=0, le=60, alias="SEARCH_EMBEDDING_QUEUE_TIMEOUT_SECONDS"
    )
    search_embedding_cache_size: int = Field(
        default=256, ge=0, le=10000, alias="SEARCH_EMBEDDING_CACHE_SIZE"
    )
    search_embedding_cache_ttl_seconds: int = Field(
        default=900, ge=1, le=86400, alias="SEARCH_EMBEDDING_CACHE_TTL_SECONDS"
    )
    search_guest_rate_limit_requests: int = Field(
        default=20, ge=1, le=10000, alias="SEARCH_GUEST_RATE_LIMIT_REQUESTS"
    )
    search_authenticated_rate_limit_requests: int = Field(
        default=60, ge=1, le=10000, alias="SEARCH_AUTHENTICATED_RATE_LIMIT_REQUESTS"
    )
    search_rate_limit_window_seconds: int = Field(
        default=60, ge=1, le=3600, alias="SEARCH_RATE_LIMIT_WINDOW_SECONDS"
    )
    search_runs_retention_days: int = Field(
        default=90, ge=1, le=3650, alias="SEARCH_RUNS_RETENTION_DAYS"
    )

    reranker_base_url: str = Field(default="http://localhost:8001", alias="RERANKER_BASE_URL")
    reranker_model: str = Field(default="Qwen/Qwen3-Reranker-0.6B", alias="RERANKER_MODEL")
    reranker_model_revision: str = Field(
        default="1f54aa72c421b677caa56ece526856f8c60144a5",
        alias="RERANKER_MODEL_REVISION",
    )
    reranker_device: Literal["cpu", "cuda"] = Field(default="cpu", alias="RERANKER_DEVICE")
    reranker_batch_size: int = Field(default=8, ge=1, le=128, alias="RERANKER_BATCH_SIZE")
    reranker_max_length: int = Field(default=768, ge=128, le=32768, alias="RERANKER_MAX_LENGTH")
    reranker_timeout_seconds: float = Field(
        default=60, gt=0, le=600, alias="RERANKER_TIMEOUT_SECONDS"
    )
    reranker_top_n: int = Field(default=8, ge=1, le=100, alias="RERANKER_TOP_N")
    reranker_required: bool = Field(default=False, alias="RERANKER_REQUIRED")
    reranker_instruction: str = Field(
        default=(
            "Given a Russian Python programming question, determine whether the passage "
            "directly helps answer the question."
        ),
        alias="RERANKER_INSTRUCTION",
    )
    reranker_fusion_blend: float = Field(default=0.15, ge=0, le=0.5, alias="RERANKER_FUSION_BLEND")
    reranker_max_concurrent_requests: int = Field(
        default=1, ge=1, le=16, alias="RERANKER_MAX_CONCURRENT_REQUESTS"
    )
    reranker_queue_timeout_seconds: float = Field(
        default=5, gt=0, le=60, alias="RERANKER_QUEUE_TIMEOUT_SECONDS"
    )

    llm_provider: Literal["ollama"] = Field(default="ollama", alias="LLM_PROVIDER")
    llm_model: str = Field(default="qwen3:8b", min_length=1, alias="LLM_MODEL")
    llm_base_url: str = Field(default="http://localhost:11434", alias="LLM_BASE_URL")
    llm_num_ctx: int = Field(default=8192, ge=1024, le=131072, alias="LLM_NUM_CTX")
    llm_temperature: float = Field(default=0.1, ge=0, le=2, alias="LLM_TEMPERATURE")
    llm_top_p: float = Field(default=0.9, gt=0, le=1, alias="LLM_TOP_P")
    llm_max_output_tokens: int = Field(default=1200, ge=64, le=8192, alias="LLM_MAX_OUTPUT_TOKENS")
    llm_timeout_seconds: float = Field(default=180, gt=0, le=1800, alias="LLM_TIMEOUT_SECONDS")
    llm_keep_alive: str = Field(default="5m", alias="LLM_KEEP_ALIVE")
    llm_max_concurrent_requests: int = Field(
        default=1, ge=1, le=16, alias="LLM_MAX_CONCURRENT_REQUESTS"
    )
    llm_queue_limit: int = Field(default=4, ge=0, le=100, alias="LLM_QUEUE_LIMIT")
    llm_queue_timeout_seconds: float = Field(
        default=15, gt=0, le=300, alias="LLM_QUEUE_TIMEOUT_SECONDS"
    )
    llm_think: bool = Field(default=False, alias="LLM_THINK")

    rag_search_mode: Literal["hybrid"] = Field(default="hybrid", alias="RAG_SEARCH_MODE")
    rag_candidate_limit: int = Field(default=80, ge=5, le=500, alias="RAG_CANDIDATE_LIMIT")
    rag_rerank_limit: int = Field(default=30, ge=1, le=100, alias="RAG_RERANK_LIMIT")
    rag_sources_limit: int = Field(default=5, ge=1, le=20, alias="RAG_SOURCES_LIMIT")
    rag_max_chunks_per_document: int = Field(
        default=2, ge=1, le=5, alias="RAG_MAX_CHUNKS_PER_DOCUMENT"
    )
    rag_context_token_budget: int = Field(
        default=5000, ge=256, le=65536, alias="RAG_CONTEXT_TOKEN_BUDGET"
    )
    rag_min_reranker_score: float = Field(default=0.25, ge=0, le=1, alias="RAG_MIN_RERANKER_SCORE")
    rag_min_source_count: int = Field(default=1, ge=1, le=20, alias="RAG_MIN_SOURCE_COUNT")
    rag_max_source_count: int = Field(default=5, ge=1, le=20, alias="RAG_MAX_SOURCE_COUNT")
    rag_min_context_tokens: int = Field(default=40, ge=1, le=4096, alias="RAG_MIN_CONTEXT_TOKENS")
    rag_reranker_required: bool = Field(default=True, alias="RAG_RERANKER_REQUIRED")
    rag_prompt_version: str = Field(default="6.3.1", alias="RAG_PROMPT_VERSION")
    rag_max_answer_characters: int = Field(
        default=16000, ge=256, le=100000, alias="RAG_MAX_ANSWER_CHARACTERS"
    )
    rag_guest_rate_limit_requests: int = Field(
        default=5, ge=1, le=1000, alias="RAG_GUEST_RATE_LIMIT_REQUESTS"
    )
    rag_authenticated_rate_limit_requests: int = Field(
        default=20, ge=1, le=1000, alias="RAG_AUTHENTICATED_RATE_LIMIT_REQUESTS"
    )
    rag_rate_limit_window_seconds: int = Field(
        default=60, ge=1, le=3600, alias="RAG_RATE_LIMIT_WINDOW_SECONDS"
    )

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
    project_disk_warning_gb: float = Field(default=27, gt=0, alias="PROJECT_DISK_WARNING_GB")
    project_disk_critical_gb: float = Field(default=30, gt=0, alias="PROJECT_DISK_CRITICAL_GB")
    project_disk_limit_gb: float = Field(default=35, gt=0, alias="PROJECT_DISK_LIMIT_GB")
    backup_retention_count: int = Field(default=3, ge=1, le=100, alias="BACKUP_RETENTION_COUNT")
    acceptance_minimum_documents: int = Field(
        default=5000, ge=5000, le=100000, alias="ACCEPTANCE_MINIMUM_DOCUMENTS"
    )
    acceptance_api_base_url: str = Field(
        default="http://backend:8000/api", alias="ACCEPTANCE_API_BASE_URL"
    )
    acceptance_demo_password: SecretStr = Field(
        default=SecretStr(""), alias="ACCEPTANCE_DEMO_PASSWORD"
    )

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
        if (
            max(
                self.search_bm25_candidates,
                self.search_vector_candidates,
                self.search_hybrid_candidates,
            )
            > self.search_max_candidates
        ):
            raise ValueError("Search candidate limit не может превышать SEARCH_MAX_CANDIDATES")
        if self.reranker_top_n > self.search_max_candidates:
            raise ValueError("RERANKER_TOP_N не может превышать SEARCH_MAX_CANDIDATES")
        if self.llm_think:
            raise ValueError("LLM_THINK должен оставаться false: hidden reasoning не выдаётся")
        if self.rag_rerank_limit > self.rag_candidate_limit:
            raise ValueError("RAG_RERANK_LIMIT не может превышать RAG_CANDIDATE_LIMIT")
        if self.rag_min_source_count > self.rag_max_source_count:
            raise ValueError("RAG_MIN_SOURCE_COUNT не может превышать RAG_MAX_SOURCE_COUNT")
        if self.rag_sources_limit > self.rag_max_source_count:
            raise ValueError("RAG_SOURCES_LIMIT не может превышать RAG_MAX_SOURCE_COUNT")
        if self.rag_context_token_budget + self.llm_max_output_tokens > self.llm_num_ctx:
            raise ValueError("RAG context и LLM output не помещаются в LLM_NUM_CTX")
        if not (
            self.project_disk_warning_gb
            < self.project_disk_critical_gb
            < self.project_disk_limit_gb
        ):
            raise ValueError("Disk thresholds должны возрастать: WARNING < CRITICAL < LIMIT")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
