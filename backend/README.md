# PyAnswer API — Этап 4 и подэтап 5.2

FastAPI backend реализует серверную аутентификацию, пользовательский контур, RBAC, редакторские
и административные операции PyAnswer. PostgreSQL является единственной runtime и integration
test DB; SQLite не используется.

Подэтапы 5.1–5.2 расширяют backend durable очередью, отдельным worker, типизированным клиентом
Stack Exchange и реальным document processing pipeline. UI и эксплуатационная приёмка Этапа 5
завершаются в 5.3.

## Стек и структура

- Python 3.12, FastAPI, Pydantic v2 и pydantic-settings;
- async SQLAlchemy 2.x, asyncpg, PostgreSQL 16 и Alembic;
- Argon2id (`argon2-cffi`), opaque server-side sessions, HttpOnly-cookie и CSRF;
- httpx для ограниченной проверки Stack Exchange source;
- Ruff, strict mypy, pytest, pytest-asyncio и coverage.

```text
backend/
  app/
    api/              dependencies, errors, pagination и тонкие routes
    core/             config, security, permissions, CSRF, middleware, logging
    db/models/        SQLAlchemy models
    db/repositories/  data access без решений о permissions
    integrations/     типизированные клиенты внешних API
    schemas/          camelCase Pydantic API schemas
    processing/       HTML cleaning, canonicalization, hashes и chunking
    services/         транзакционные бизнес-правила, ingestion и audit
    seed/             идемпотентные bootstrap/demo seed функции
    scripts/          CLI entry points
    worker.py          отдельный lifecycle фонового worker
  alembic/            async environment и начальная migration
  tests/unit/         чистая security/domain логика
  tests/integration/  реальные PostgreSQL HTTP/service scenarios
```

## Environment

Скопируйте `.env.example` в `.env` и замените placeholders. Обязательные группы:

- приложение: `APP_ENV`, `APP_NAME`, `APP_VERSION`, `DEBUG`, `DOCS_ENABLED`;
- БД: `DATABASE_URL`, отдельный `TEST_DATABASE_URL`;
- CORS: JSON-массив `FRONTEND_ORIGINS` без wildcard;
- cookie/session: имена cookie, TTL, `COOKIE_SECURE`, `COOKIE_SAMESITE`;
- Argon2: time/memory/parallelism cost;
- bootstrap: admin email/name/password из окружения;
- seed/source: `SEED_DEMO_DATA`, site, tag и target documents;
- Stack Exchange: allowlisted API URL, optional key, filters, page/rate/timeout/retry/quota limits;
- worker: poll interval, lease, heartbeat, max attempts и graceful shutdown timeout;
- rate limit: число auth attempts и окно.

Production-конфигурация отклоняет insecure cookie, default database credentials и включённый
demo seed. `STACKEXCHANGE_KEY` можно оставить пустым; он читается только из environment и не
попадает в БД или API. Настоящие пароли и `.env` не коммитятся.

## Локальная установка

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

Запустите PostgreSQL и укажите asyncpg URL:

```bash
export DATABASE_URL='postgresql+asyncpg://pyanswer:your-password@localhost:5432/pyanswer'
.venv/bin/alembic upgrade head
.venv/bin/python -m app.scripts.bootstrap
.venv/bin/uvicorn app.main:app --reload
```

Bootstrap идемпотентно создаёт roles, permissions, role-permission matrix, singleton system
settings, основной source и опционального admin из environment. Development seed запускается
отдельно:

```bash
SEED_DEMO_DATA=true .venv/bin/python -m app.scripts.seed_demo
```

Seed не удаляет и не перезаписывает существующих пользователей. Он создаёт три demo account,
10 synthetic users, 20 документов с ответами/тегами, history, saved, feedback, jobs и audit.

## Миграции

```bash
.venv/bin/alembic upgrade head
.venv/bin/alembic current
.venv/bin/alembic history
.venv/bin/alembic check
```

`downgrade -1` проверяется только на disposable test DB. Initial migration создаёт схему без seed
и паролей; migration `20260716_0002` добавляет worker queue, source checkpoint, events и ingestion
failures. Migration `20260716_0003` добавляет processing/dedup fields, answer reconciliation,
`document_revisions` и `document_chunks`. Upgrade/downgrade транзакционны для PostgreSQL.

## Worker и Stack Exchange

Worker запускается отдельно командой `python -m app.worker`. Он атомарно захватывает jobs через
`FOR UPDATE SKIP LOCKED`, фиксирует claim и выполняет сетевую работу вне транзакции. Lease и
heartbeat позволяют восстановить stale job, а cancellation обрабатывается в безопасной точке с
сохранением последнего committed checkpoint.

Stack Exchange client использует один `httpx.AsyncClient` на lifecycle worker, pagesize не более
100 и batch answers не более 100 question ID. Он соблюдает `has_more`, wrapper backoff,
`Retry-After`, quota reserve, ограниченные retries и response size limit. Test connection делает
один малый request и не сохраняет documents.

На 5.2 `SOURCE_SYNC` выполняет INITIAL/INCREMENTAL загрузку, batch answers, очистку, upsert
documents/answers/tags, exact deduplication, revisions и deterministic chunks. Dry-run остаётся
доступным и изолирован от production sync state. Подробности:

- [worker architecture](../docs/worker-architecture.md);
- [Stack Exchange client](../docs/stackexchange-client.md);
- [ingestion 5.2](../docs/stage5-ingestion.md);
- [content cleaning](../docs/content-cleaning.md);
- [chunking](../docs/chunking.md).

Checkpoint фиксируется только после committed batch и содержит page + item offset. Это позволяет
ограничить smoke-run внутри страницы из 100 вопросов без пропуска оставшихся элементов. Ошибка
качества одного thread сохраняется в `ingestion_failures`; ошибка схемы/API/БД останавливает или
ограниченно requeue всей job.

Canonical content и metadata хешируются SHA-256 отдельно. Metadata-only update не создаёт новую
revision/chunks. Смысловое изменение увеличивает document version. Успешная обработка оставляет
BM25/vector в `NOT_INDEXED`/`OUTDATED`, никогда не имитируя готовый индекс.

## Security model

### Passwords

Сервер повторно проверяет policy: не менее 8 символов, одна lowercase, uppercase и цифра. Raw
password живёт только в request/service call, не сохраняется и не логируется. В `users` хранится
Argon2id hash; API, ADMIN response и audit его никогда не возвращают. После успешного login
поддерживается rehash при изменении параметров Argon2.

### Sessions и CSRF

Login генерирует случайные session и CSRF tokens. PostgreSQL хранит только SHA-256 hashes.
Session reference отправляется в `HttpOnly`, `SameSite` cookie; CSRF token — в readable cookie и
response `/api/auth/csrf`. Unsafe запрос отправляет `X-CSRF-Token`. Middleware проверяет
double-submit, а dependency для authenticated mutation дополнительно сравнивает token hash с
session record.

Session отклоняется, если она expired/revoked, user BLOCKED или `session.account_version` не
совпадает с user. Role change/block увеличивают account version и отзывают целевые sessions.
Logout требует CSRF, отзывает запись и удаляет обе cookie.

### RBAC

Permissions загружаются только по цепочке `session → user → role → role_permissions`. Role,
permission, query/header/payload клиента не считаются доверенными. USER получает search/profile/
history/saved; EDITOR наследует USER и управляет документами; ADMIN наследует обе группы и
управляет users/sources/jobs/audit/system.

Self-role-change и self-block запрещены. Изменение ADMIN выполняется под PostgreSQL advisory
transaction lock и row lock, поэтому concurrent requests не могут обойти правило активного
администратора. Успешная операция и audit фиксируются одной request transaction.

### HTTP boundary

CORS разрешает только `FRONTEND_ORIGINS` с credentials. Каждый response содержит request ID и
security headers. Ошибки имеют безопасный envelope; production не возвращает stack traces.
Structured access log не содержит cookies, Authorization или request body.

## Основные API

- auth: `/api/auth/csrf`, register, login, logout, me;
- user: `/api/users/me`, stats, history, saved, feedback, public document;
- editor: dashboard, managed documents, metadata, hide/restore/reindex, bulk, jobs;
- admin: dashboard, users, sources, jobs, audit, system/status/settings;
- ingestion 5.2: source sync/checkpoint, read-only job events, stats и безопасные failures;
- operations: `/api/health/live`, `/api/health/ready`;
- placeholders: `/api/search` и `/api/ask` возвращают 501.

Полный flow и список routes находятся в [docs/api-contract.md](../docs/api-contract.md). OpenAPI
доступен в development по `/api/docs`; production может отключить его.

## Тесты

Integration tests требуют отдельный PostgreSQL URL, содержащий `test`. Fixture намеренно
отказывается запускаться против другого имени и очищает только disposable DB.

```bash
export TEST_DATABASE_URL='postgresql+asyncpg://pyanswer_test:password@localhost:55432/pyanswer_test'
export DATABASE_URL="$TEST_DATABASE_URL"
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app
.venv/bin/pytest --cov=app --cov-report=term-missing --cov-fail-under=80
```

Внешний Stack Exchange HTTP полностью mock-ируется в обычных tests.

## Docker

Корневой `compose.yaml` содержит PostgreSQL, backend и отдельный worker на том же backend image:

```bash
docker compose up -d postgres
docker compose run --rm backend alembic upgrade head
docker compose run --rm backend python -m app.scripts.bootstrap
docker compose run --rm backend python -m app.scripts.seed_demo
docker compose up backend
docker compose up -d worker
```

Backend image запускается non-root пользователем и имеет healthcheck. Migration не запускается
автоматически вместе с API или worker.

Makefile автоматически выбирает рабочий `docker compose` или `docker-compose`; выбор можно
переопределить через `COMPOSE=...`:

```bash
make worker-up
make worker-health
make worker-logs
make COMPOSE=docker-compose worker-up
```

## Этап 5 и ограничения

SOURCE_SYNC сохраняет questions, answers, tags, revisions и chunks; worker поддерживает durable
claim, lease, heartbeat, checkpoint, cancellation и retry. Operational API и CLI описаны в
`docs/stage5-ingestion.md` и `docs/ingestion-runbook.md`. Полный импорт 25 000 документов требует
явного `CONFIRM_FULL_SYNC=YES` и автоматически не запускается.

RAG ещё не настроен и `/api/ask` честно возвращает 501. Frontend mock mode остаётся
демонстрационным режимом по умолчанию.

## Stage 6.1–6.2

Добавлены Qdrant 1.18.2, Ollama embeddings, отдельный indexer, versioned collections и
blue-green alias switch. `/api/search` выполняет реальный BM25/vector/hybrid retrieval,
weighted RRF и optional local reranking. PostgreSQL повторно проверяет visibility/version перед
выдачей. Команды: `make qdrant-up`, `make embedding-model-pull`, `make indexer-up`,
`make reranker-model-pull`, `make reranker-up`, `make search-evaluate`.
