# ER-диаграмма PyAnswer Этапа 4

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
  DOCUMENTS ||--o{ ANSWERS : contains
  DOCUMENTS ||--o{ DOCUMENT_TAGS : tagged
  TAGS ||--o{ DOCUMENT_TAGS : classifies
  DOCUMENTS ||--o{ SAVED_DOCUMENTS : saved
  DOCUMENTS ||--o{ JOBS : reindexed
  JOBS ||--o{ JOBS : retried_as
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
    string type
    string status
    jsonb payload
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
`document_tags`. Preferences — 1:1. History/saved/feedback строго принадлежат user. Audit является
append-only на уровне публичного API.
