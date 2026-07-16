# PyAnswer — исходное задание Этапа 4

Этот файл хранит нормализованную копию полученного задания, чтобы требования этапа не зависели
от истории чата. Фактический код Этапов 1–3 и существующий TypeScript API interface являются
источником истины; frontend нельзя переписывать или ломать.

## Цель

Создать настоящий backend на Python 3.12: FastAPI, Pydantic v2, async SQLAlchemy 2.x,
asyncpg/PostgreSQL, Alembic, Argon2id, server-side opaque sessions, HttpOnly-cookie, CSRF,
серверный RBAC, audit, user/editor/admin API, Docker и тесты. Сохранить `VITE_USE_MOCKS=true`.
При HTTP-режиме `/api/search` и `/api/ask` честно возвращают соответственно
`501 SEARCH_ENGINE_NOT_READY` и `501 RAG_ENGINE_NOT_READY` до Этапа 6.

На этом этапе запрещены настоящий Stack Exchange parser/crawler/indexer, Qdrant, embeddings,
BM25/HNSW/hybrid/reranker, Ollama/RAG, Celery/Redis без необходимости и финальная production
инфраструктура.

## Backend и структура

- Каталог `backend/`, `pyproject.toml`, Python 3.12.
- FastAPI, Uvicorn, Pydantic v2, pydantic-settings, async SQLAlchemy, asyncpg, Alembic,
  PostgreSQL, argon2-cffi, httpx, email-validator, pytest/pytest-asyncio/pytest-cov, Ruff, mypy.
- Слои `api/routes`, `core`, `db/models`, `db/repositories`, `schemas`, `services`, `scripts`,
  `seed`, `utils`; routes тонкие, permissions и бизнес-правила не находятся в repositories.
- Команды: `python -m pip install -e ".[dev]"`, `ruff check .`, `ruff format --check .`,
  `mypy app`, `pytest`, coverage не ниже 80%, `alembic upgrade head`.
- Нельзя использовать SQLite как production/integration DB, Django/Flask, SaaS auth, Bearer
  из browser storage, открытые пароли.

## Конфигурация

Environment через pydantic-settings: `APP_ENV`, `APP_NAME`, `APP_VERSION`, `DEBUG`,
`DATABASE_URL`, `TEST_DATABASE_URL`, `FRONTEND_ORIGINS`, cookie names/TTL/Secure/SameSite,
Argon2 costs, bootstrap-admin fields, `SEED_DEMO_DATA`, Stack Exchange site/tag/target.
`.env.example` содержит только placeholders. Production обязан завершаться с понятной ошибкой
при небезопасной/неполной конфигурации.

## PostgreSQL schema

Обязательны таблицы и связи:

- `roles`, `permissions`, `role_permissions`;
- `users` с normalized unique email, role/status/account_version и блокировкой;
- `sessions` только с hash session/CSRF tokens, expiry/revocation/account_version;
- `user_preferences` 1:1;
- `sources`;
- `documents` с исходными и редакторскими полями/status/index statuses/version;
- `answers`, `tags`, `document_tags`;
- `search_history`, `saved_documents`, `feedback`;
- `jobs` (на Этапе 4 только durable записи без worker);
- immutable-through-API `audit_events`;
- singleton `system_settings`.

Нужны UUID, UTC timestamps, FK/unique/check/index constraints, осторожные cascade, отсутствие
N+1 в основных endpoints. Python/DB используют snake_case, JSON — camelCase aliases. ORM
объекты нельзя возвращать напрямую.

## Alembic, bootstrap и seed

- Async Alembic, начальная миграция всей схемы, корректные upgrade/downgrade/check/current,
  никакого seed или demo password внутри migration.
- Идемпотентные `python -m app.scripts.bootstrap` и `python -m app.scripts.seed_demo`.
- Bootstrap создаёт role/permission matrix, system settings и bootstrap ADMIN.
- Development seed (запрещён по умолчанию в production) создаёт основной source, USER/EDITOR/
  ADMIN (`user|editor|admin@pyanswer.local`, `Demo123!`), 10+ synthetic users, текущие documents,
  answers/tags/jobs/audit/history/saved/feedback; не удаляет и не перезаписывает изменённые данные.

## Server RBAC

Permission enum полностью повторяет frontend:

- USER: `SEARCH_USE`, `RAG_USE`, `PROFILE_MANAGE`, `HISTORY_MANAGE`, `SAVED_MANAGE`;
- EDITOR наследует USER и получает `EDITOR_ACCESS`, `MANAGED_DOCUMENTS_VIEW`,
  `DOCUMENT_METADATA_EDIT`, `DOCUMENT_STATUS_CHANGE`, `DOCUMENT_REINDEX`, `EDITOR_JOBS_VIEW`;
- ADMIN наследует всё и получает `ADMIN_ACCESS`, `USERS_MANAGE`, `SOURCES_MANAGE`,
  `ADMIN_JOBS_MANAGE`, `AUDIT_VIEW`, `SYSTEM_VIEW`, `SYSTEM_SETTINGS_MANAGE`.

Dependencies: optional/current/active user, require one/any/all permissions. Права определяются
только через `session → user → role → role_permissions`, а не URL/body/header/frontend role.

## Passwords, sessions и CSRF

- Argon2id, серверная password policy: 8+ символов, lower/upper/digit, case-insensitive email,
  optional rehash on login. Raw password не хранится/логируется/audit-ится/возвращается.
- Login создаёт криптографический opaque token, в DB хранится только SHA-256 hash; cookie
  HttpOnly, configurable Secure, SameSite Lax или строже, Path `/`, Max-Age зависит от remember.
- Сессия проверяет expiry/revocation/ACTIVE/account_version. Logout отзывает запись и cookies.
  Role change/block повышает account_version и отзывает target sessions.
- `GET /api/auth/csrf` выдаёт/rotates CSRF, unsafe methods требуют `X-CSRF-Token`, token
  сравнивается constant-time. Login rotates CSRF. Frontend получает token перед mutations и
  делает максимум один retry после безопасного refresh.

## HTTP security и errors

- CORS только `FRONTEND_ORIGINS`, credentials true, без wildcard.
- Request-ID middleware и `X-Request-ID` во всех responses/errors.
- Headers: nosniff, referrer policy, frame protection/CSP, HSTS только secure production.
- Structured logging: timestamp/level/message/requestId/method/path/status/duration/userId,
  без body/password/session/CSRF/cookie/Authorization/secrets.
- Error envelope: `{ "error": { "code", "message", "details", "requestId" } }`.
  Коды минимум 400/401/403/404/409/422/429/500 и два честных 501. SQL/stack traces наружу не
  попадают.

## API

Auth:

- `GET /api/auth/csrf`
- `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`
- `GET /api/auth/me`

Registration всегда создаёт USER/preferences/session/audit и игнорирует попытку передать role.
Login нейтрально сообщает о неверных credentials, проверяет ACTIVE, обновляет activity/audit.
Нужен отделённый, тестируемый single-instance auth rate limiter.

User contour:

- `GET/PATCH /api/users/me`, `GET /api/users/me/stats`;
- `GET /api/history`, `DELETE /api/history/{id}`, `DELETE /api/history`;
- `GET /api/saved`, `POST/DELETE /api/saved/{documentId}`;
- `POST /api/feedback`, `DELETE /api/feedback/{id}`,
  `GET /api/feedback/by-response/{responseId}`;
- `GET /api/documents/{documentId}`.

Данные строго изолированы по текущему user. Save/unsave идемпотентны; feedback — upsert по
user+response; USER не получает HIDDEN/PENDING/FAILED content или hiddenReason.

Editor:

- dashboard;
- managed documents list/detail/metadata;
- hide/restore/reindex/bulk;
- read-only jobs.

Metadata не меняет исходный content, version и editor timestamps обновляются, hide требует
reason, reindex создаёт только QUEUED job, active duplicate защищён constraint; bulk максимум
100, per-item partial result и batch audit. Настоящий indexer не запускается.

Admin users:

- list/detail/role/block/unblock;
- credential fields никогда не возвращаются;
- self-block/self-demotion запрещены;
- минимум один ACTIVE ADMIN защищён PostgreSQL transaction/locking от race;
- role/block повышают account_version, revoke sessions и audit в той же transaction.

Sources:

- list/detail/update/test/sync/stop;
- validation target 5000+, additional answers 0..3, page size 1..100;
- disabled source и duplicate active sync запрещены;
- test connection — ограниченный timeout httpx call, полностью mock-ированный в tests;
- sync/stop лишь создают/меняют DB jobs, без парсинга.

Admin jobs:

- list/detail/retry/cancel/full-reindex;
- completed нельзя cancel, running/completed нельзя retry, failed/cancelled можно;
- retry создаёт новую запись с retryOf; duplicate active full reindex запрещён constraint;
- никаких фоновых вычислений в HTTP request.

Audit:

- read-only list/detail для `AUDIT_VIEW`, filters/pagination;
- recursive sanitizer удаляет password/hash/salt/digest/session/CSRF/cookie/auth/secret/API key;
- success audit атомарен с business transaction и содержит requestId.

System:

- status/health-check/settings get+patch;
- FastAPI/PostgreSQL проверяются реально; Qdrant/Ollama/Crawler/Indexer/BM25/HNSW/models/reranker
  обозначаются not configured/offline, не ONLINE;
- settings находятся в PostgreSQL и реально ограничивают guest search/RAG и rag source limit.

Dashboards рассчитываются SQL aggregate/JOIN/GROUP BY, не выгрузкой всех строк в Python.
Pagination совместима с frontend, page с 1, bounded limit, stable secondary id sort, whitelist sort,
parameterized ORM only.

## Frontend HTTP integration

Mock adapter сохраняется и остаётся default. HTTP adapter использует `credentials: include`,
CSRF, AbortSignal, camelCase/filters serialization, backend envelope → `ApiError`, корректные
401/403, один CSRF retry, никакого Bearer/token storage/fetch вне API layer. При server-side
invalidation очищается auth и role-sensitive TanStack cache без redirect loop.

## Docker и health

Корневой `compose.yaml`: только `postgres` и `backend`; official PostgreSQL, named volume,
healthcheck, password только environment, configurable port. Backend non-root, depends on DB
health, port 8000, graceful shutdown, migration запускается отдельной командой. Добавить Makefile.
Health: `/api/health/live` без DB query, `/api/health/ready` проверяет PostgreSQL и отдаёт 503.

## Tests и проверки

Integration tests используют только отдельный PostgreSQL `TEST_DATABASE_URL`, защищённый словом
`test`; migrations применяются перед tests, fixtures не очищают dev/prod DB. Внешний HTTP mock.
Не менее 80% meaningful backend coverage. Обязательные сценарии: Argon2/session/CSRF/cookies/CORS,
auth/rate limit/RBAC, profile, last-admin concurrency/session revocation, history/saved/feedback
isolation, hidden documents/editor atomic audit, jobs/sources conflicts, audit sanitizer/system,
health, pagination/error/OpenAPI aliases и честные 501.

Frontend дополнительно тестирует CSRF header, credentials, 401/403/envelope, mock/HTTP selection,
cache invalidation и отсутствие бесконечного retry. Все старые tests сохраняются.

Финальные команды: backend Ruff/format/mypy/pytest+coverage, Alembic upgrade/current/check и
disposable downgrade/re-upgrade; frontend typecheck/lint/test/build/format; compose config/build,
PostgreSQL migration/bootstrap/seed, API smoke и при возможности browser manual сценарии.

## Документация и Git

Создать `backend/README.md`, `docs/backend-stage4.md`, `docs/erd.md` с Mermaid,
`docs/sql_examples.sql` (8 требуемых JOIN/GROUP BY/subquery примеров), `docs/api-contract.md`,
обновить root README. OpenAPI development docs с summary/operationId/models/errors/tags.

Нельзя оставлять TODO/FIXME/skips, SQLite, raw SQL concatenation, explicit unjustified Any,
secret logging, global active DB session, success audit after rollback, fake search/RAG.

После всех проверок один коммит:

`Реализован четвертый этап: FastAPI, PostgreSQL и серверная авторизация`

Push/force/history rewrite запрещены; итоговое дерево чистое. Не переходить к Этапу 5.
