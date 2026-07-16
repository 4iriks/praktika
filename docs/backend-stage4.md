# PyAnswer — Этап 4

## Результат

Этап 4 добавляет настоящий FastAPI/PostgreSQL boundary к существующему frontend. Mock adapter не
удалён: `VITE_USE_MOCKS=true` сохраняет демонстрационный поиск, а HTTP adapter подключает auth,
profile, saved, feedback и management API к backend.

Backend разделён на HTTP routes, Pydantic schemas, services, repositories и SQLAlchemy models.
Одна `AsyncSession` создаётся на request, commit выполняется только после успешного route, при
исключении — rollback. ORM entities не используются как response models.

## Данные

Initial Alembic revision создаёт:

- security: `roles`, `permissions`, `role_permissions`, `users`, `sessions`;
- user contour: `user_preferences`, `search_history`, `saved_documents`, `feedback`;
- corpus: `sources`, `documents`, `answers`, `tags`, `document_tags`;
- operations: `jobs`, `audit_events`, `system_settings`.

UUID применяются для domain entities, UTC timestamp — для событий. Foreign keys, unique/check
constraints и indexes закрепляют email uniqueness, one-feedback-per-response,
one-saved-document-per-user и допустимые enum/status значения.

## Auth sequence

1. Client получает `/api/auth/csrf`.
2. Unsafe request отправляет readable cookie и `X-CSRF-Token`.
3. Register/login проверяет credentials, создаёт opaque session и ротирует CSRF.
4. БД получает только SHA-256 token hashes и Argon2id password hash.
5. HttpOnly session cookie не читается JavaScript.
6. Auth dependency проверяет revoked/expiry/status/account version.
7. Logout или admin role/status mutation отзывают session.

## Server RBAC

Permission matrix совпадает по кодам с frontend, но рассчитывается независимо из таблиц БД.
Dependencies обеспечивают 401/403, services повторно соблюдают self-action, last-admin, document
status и active-job rules. UI visibility никогда не считается защитой.

Критические операции используют request transaction. Last ACTIVE ADMIN защищён PostgreSQL
advisory transaction lock и locked target row. Active reindex/source/full-reindex jobs защищены
partial unique indexes, поэтому race не обходится предварительным SELECT.

## Audit

Audit создаётся service layer в той же transaction. Recursive sanitizer удаляет поля, содержащие
password/hash/salt/digest/session/csrf/cookie/authorization/secret/api key/token. Публичного
update/delete API нет.

## System truthfulness

Backend и PostgreSQL проверяются реально. Qdrant, Ollama, crawler, indexer, BM25/vector index,
embedding model и reranker возвращаются как OFFLINE/not configured. Hardware telemetry не
выдумывается. Search/ask возвращают `SEARCH_ENGINE_NOT_READY` и `RAG_ENGINE_NOT_READY` с HTTP 501.

## Следующие этапы

Этап 5 добавит Stack Exchange ingestion worker и durable job lifecycle. Search indexes и RAG
появятся позднее; текущая PostgreSQL-схема уже содержит source/document/job metadata для этого.
