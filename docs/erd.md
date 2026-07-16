# ER-диаграмма PyAnswer — Этап 4 и подэтап 5.1

```mermaid
erDiagram
  ROLES ||--o{ USERS : assigns
  ROLES ||--o{ ROLE_PERMISSIONS : grants
  PERMISSIONS ||--o{ ROLE_PERMISSIONS : contains
  USERS ||--o{ SESSIONS : owns
  USERS ||--|| USER_PREFERENCES : configures
  USERS ||--o{ SEARCH_HISTORY : creates
  USERS ||--o{ SAVED_DOCUMENTS : saves
  USERS ||--o{ FEEDBACK : submits
  USERS ||--o{ JOBS : creates
  USERS ||--o{ AUDIT_EVENTS : acts
  SOURCES ||--o{ DOCUMENTS : provides
  SOURCES ||--o{ JOBS : syncs
  SOURCES ||--o| SOURCE_SYNC_STATES : checkpoints
  SOURCES ||--o{ INGESTION_FAILURES : reports
  DOCUMENTS ||--o{ ANSWERS : contains
  DOCUMENTS ||--o{ DOCUMENT_TAGS : tagged
  TAGS ||--o{ DOCUMENT_TAGS : classifies
  DOCUMENTS ||--o{ SAVED_DOCUMENTS : saved
  DOCUMENTS ||--o{ JOBS : reindexed
  JOBS ||--o{ JOBS : retried_as
  JOBS ||--o{ JOB_EVENTS : emits
  JOBS ||--o{ INGESTION_FAILURES : records
  WORKER_INSTANCES ||--o{ JOBS : claims
  WORKER_INSTANCES }o--o| JOBS : currently_runs
  USERS ||--o{ SYSTEM_SETTINGS : updates

  ROLES {
    uuid id PK
    string code UK
    string name
  }
  PERMISSIONS {
    uuid id PK
    string code UK
  }
  ROLE_PERMISSIONS {
    uuid role_id PK,FK
    uuid permission_id PK,FK
  }
  USERS {
    uuid id PK
    uuid role_id FK
    string normalized_email UK
    string password_hash
    string status
    int account_version
  }
  SESSIONS {
    uuid id PK
    uuid user_id FK
    string token_hash UK
    string csrf_token_hash
    timestamptz expires_at
    timestamptz revoked_at
  }
  USER_PREFERENCES {
    uuid user_id PK,FK
    string default_search_mode
    string default_search_view
  }
  SOURCES {
    uuid id PK
    string name
    string type
    string status
    uuid current_job_id FK
    int rate_limit_remaining
    int rate_limit_total
    timestamptz rate_limit_updated_at
  }
  DOCUMENTS {
    uuid id PK
    uuid source_id FK
    string external_id
    string status
    string bm25_status
    string vector_status
    int version
  }
  ANSWERS {
    uuid id PK
    uuid document_id FK
    string external_id
    boolean is_accepted
  }
  TAGS {
    uuid id PK
    string normalized_name UK
  }
  DOCUMENT_TAGS {
    uuid document_id PK,FK
    uuid tag_id PK,FK
    boolean is_managed PK
  }
  SEARCH_HISTORY {
    uuid id PK
    uuid user_id FK
    jsonb filters
  }
  SAVED_DOCUMENTS {
    uuid user_id PK,FK
    uuid document_id PK,FK
  }
  FEEDBACK {
    uuid id PK
    uuid user_id FK
    string response_id
    string value
  }
  JOBS {
    uuid id PK
    uuid source_id FK
    uuid document_id FK
    uuid created_by FK
    uuid retry_of_job_id FK
    uuid claimed_by FK
    string type
    string status
    string stage
    timestamptz lease_expires_at
    timestamptz heartbeat_at
    int attempt
    int max_attempts
    timestamptz next_attempt_at
    timestamptz cancellation_requested_at
    jsonb payload
    jsonb checkpoint
    jsonb result
    int request_count
    int bytes_received
  }
  SOURCE_SYNC_STATES {
    uuid source_id PK,FK
    timestamptz initial_sync_completed_at
    timestamptz initial_snapshot_todate
    int next_page
    timestamptz incremental_watermark
    string current_mode
    timestamptz last_checkpoint_at
    uuid last_job_id FK
    jsonb state
  }
  WORKER_INSTANCES {
    uuid id PK
    string instance_id UK
    string name
    jsonb capabilities
    string status
    uuid current_job_id FK
    timestamptz heartbeat_at
  }
  JOB_EVENTS {
    uuid id PK
    uuid job_id FK
    string level
    string stage
    string code
    string message
    jsonb metrics
    timestamptz created_at
  }
  INGESTION_FAILURES {
    uuid id PK
    uuid job_id FK
    uuid source_id FK
    string external_id
    string entity_type
    string error_code
    boolean retryable
    jsonb context
    timestamptz resolved_at
  }
  AUDIT_EVENTS {
    uuid id PK
    uuid actor_user_id FK
    string request_id
    jsonb before
    jsonb after
  }
  SYSTEM_SETTINGS {
    int singleton_id PK
    uuid updated_by FK
    boolean allow_guest_search
    boolean allow_guest_rag
  }
```

`users ↔ permissions` является N:M через role. `documents ↔ tags` — N:M через
`document_tags`. Preferences и source sync state — связи 1:1. History/saved/feedback строго
принадлежат user. Audit является append-only на уровне публичного API.

`jobs.claimed_by` указывает на зарегистрированный worker, а
`worker_instances.current_job_id` отражает его текущую job. Эти ссылки nullable, чтобы stale
recovery и остановка worker не удаляли durable job. `job_events` и `ingestion_failures` не
содержат API key, cookies, tokens или полный ответ Stack Exchange.

Таблицы revisions/chunks и дополнительные processing-поля документов будут добавлены в 5.2;
эта диаграмма не объявляет весь Этап 5 завершённым.
