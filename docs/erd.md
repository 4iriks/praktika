# ER-диаграмма PyAnswer — Этап 4 и подэтап 5.2

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
  DOCUMENTS ||--o{ DOCUMENT_REVISIONS : versions
  DOCUMENTS ||--o{ DOCUMENT_CHUNKS : splits
  ANSWERS ||--o{ DOCUMENT_CHUNKS : attributes
  DOCUMENTS ||--o{ DOCUMENTS : duplicate_of
  DOCUMENTS ||--o{ INGESTION_FAILURES : concerns
  DOCUMENTS ||--o{ SAVED_DOCUMENTS : saved
  DOCUMENTS ||--o{ JOBS : reprocessed
  JOBS ||--o{ JOBS : retry_of
  JOBS ||--o{ JOB_EVENTS : emits
  JOBS ||--o{ INGESTION_FAILURES : records
  WORKER_INSTANCES ||--o{ JOBS : claims
  WORKER_INSTANCES }o--o| JOBS : currently_runs
  USERS ||--o{ SYSTEM_SETTINGS : updates

  SOURCES {
    uuid id PK
    string name UK
    string status
    uuid current_job_id FK
    int documents_count
    int rate_limit_remaining
  }
  SOURCE_SYNC_STATES {
    uuid source_id PK,FK
    timestamptz initial_sync_completed_at
    timestamptz incremental_watermark
    int next_page
    string current_mode
    uuid last_job_id FK
    jsonb state
  }
  DOCUMENTS {
    uuid id PK
    uuid source_id FK
    string external_id
    uuid duplicate_of_document_id FK
    string status
    string processing_status
    string deduplication_status
    string content_hash
    string metadata_hash
    int version
    int chunks_count
  }
  ANSWERS {
    uuid id PK
    uuid document_id FK
    string external_id
    string body_hash
    boolean selected_for_corpus
    int selection_rank
    boolean source_missing
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
  DOCUMENT_REVISIONS {
    uuid id PK
    uuid document_id FK
    int version
    string content_hash
    string metadata_hash
    jsonb snapshot
  }
  DOCUMENT_CHUNKS {
    uuid id PK
    string chunk_key UK
    uuid document_id FK
    uuid answer_id FK
    int document_version
    int ordinal
    string section_type
    string content_hash
  }
  JOBS {
    uuid id PK
    uuid source_id FK
    uuid document_id FK
    uuid retry_of_job_id FK
    uuid claimed_by FK
    string type
    string status
    timestamptz lease_expires_at
    jsonb checkpoint
    jsonb result
  }
  JOB_EVENTS {
    uuid id PK
    uuid job_id FK
    string level
    string stage
    string code
    jsonb metrics
  }
  WORKER_INSTANCES {
    uuid id PK
    string instance_id UK
    jsonb capabilities
    string status
    uuid current_job_id FK
    timestamptz heartbeat_at
  }
  INGESTION_FAILURES {
    uuid id PK
    uuid job_id FK
    uuid source_id FK
    uuid document_id FK
    string external_id
    string error_code
    boolean retryable
    jsonb context
  }
```

`documents ↔ tags` — N:M через `document_tags`; source sync state — 1:1. Duplicate — nullable
self-reference, retry — self-reference job. Revisions и chunks удаляются только вместе с
document. Answers физически сохраняются и reconciliation использует `source_missing`.

Credential/session/API key отсутствуют в ingestion tables, checkpoints, events и failures.
# Дополнение Этапа 6.1

```mermaid
erDiagram
  JOBS ||--o| SEARCH_INDEX_VERSIONS : builds
  USERS ||--o{ SEARCH_INDEX_VERSIONS : creates
  SEARCH_INDEX_VERSIONS ||--o{ SEARCH_INDEX_ENTRIES : contains
  DOCUMENT_CHUNKS ||--o{ SEARCH_INDEX_ENTRIES : indexed_as
  DOCUMENTS ||--o{ SEARCH_INDEX_ENTRIES : groups
```

`search_index_versions` хранит version/config/status физической Qdrant collection. `search_index_entries` — идемпотентное соответствие PostgreSQL chunk → Qdrant point; vectors в PostgreSQL не дублируются.
