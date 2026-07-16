# ПРОМТ 5.1 — worker, очередь заданий и клиент Stack Exchange

```text
Продолжай разработку существующего проекта PyAnswer.

Ты работаешь над подэтапом 5.1. Это первая часть Этапа 5.

Не создавай проект заново. Не переписывай frontend или backend. Не удаляй функции Этапов 1–4.

Исходное состояние подтверждено:

- Этап 4 завершён коммитом ccef37aa01f1e6b60b2bfd2c697450c153032ef4;
- ветка main;
- рабочее дерево перед началом должно быть чистым;
- backend: FastAPI, PostgreSQL, SQLAlchemy 2.x, Alembic;
- серверные сессии, Argon2id, CSRF и RBAC уже реализованы;
- frontend HTTP adapter и mock adapter существуют;
- /api/search и /api/ask пока возвращают 501;
- PostgreSQL и backend уже описаны в compose.yaml;
- текущие backend и frontend проверки проходят.

Сначала изучи фактическую архитектуру:

- git status, branch и log;
- compose.yaml и Dockerfile backend;
- backend/pyproject.toml;
- app/core/config.py;
- SQLAlchemy models и Alembic;
- jobs, sources, audit и system services;
- admin source/jobs endpoints;
- существующие permissions;
- frontend source/jobs/system pages;
- текущие тесты и документацию.

Фактический код является источником истины. Не создавай параллельные дублирующие модели, если аналог уже существует.

==================================================
ЦЕЛЬ ПОДЭТАПА 5.1
==================================================

Создать надёжную инфраструктуру фонового парсинга:

1. Отдельный worker-процесс.
2. Durable очередь заданий в PostgreSQL.
3. Атомарный claim через FOR UPDATE SKIP LOCKED.
4. Lease, heartbeat, graceful shutdown и восстановление stale jobs.
5. Cancellation и ограниченные retries.
6. Типизированный асинхронный Stack Exchange API client.
7. Пагинация вопросов и ответов.
8. Соблюдение has_more, backoff, quota и Retry-After.
9. Source sync checkpoint и job events.
10. Реальный test connection.
11. Docker-сервис worker.
12. Полные unit/integration tests инфраструктуры.

На подэтапе 5.1 ещё НЕ реализуй полный document processing pipeline, окончательную очистку, дедупликацию и чанкинг. Они будут завершены в 5.2.

Не подключай:

- Qdrant;
- embeddings;
- BM25;
- HNSW;
- reranker;
- Ollama;
- LLM;
- Redis;
- Celery.

Не запускай полный импорт 25 000 документов.

==================================================
1. ОБЩИЕ ПРАВИЛА
==================================================

- Не выполнять длительный парсинг внутри HTTP request.
- Не использовать FastAPI BackgroundTasks для SOURCE_SYNC.
- Не держать DB transaction открытой во время HTTP-запроса или sleep.
- Не создавать глобальные бесконечные timers.
- Не допускать выполнение одной job двумя worker-процессами.
- Не устанавливать BM25/vector status в READY.
- Не имитировать поиск или RAG.
- Все внешние HTTP-вызовы в автоматических тестах должны быть mock-ированы.
- API key не должен попадать в БД, audit, job payload, job events, logs, frontend или Git.

==================================================
2. MIGRATION 5.1
==================================================

Создай новую Alembic migration, расширяющую существующую схему.

Аккуратно расширь существующую таблицу jobs. Добавь отсутствующие поля:

- claimed_by;
- claimed_at;
- lease_expires_at;
- heartbeat_at;
- attempt;
- max_attempts;
- next_attempt_at;
- cancellation_requested_at;
- checkpoint JSONB;
- result JSONB;
- request_count;
- bytes_received;
- updated_at.

Сохрани все существующие поля и совместимость API.

Создай таблицу source_sync_states, связь 1:1 с sources:

- source_id PK/FK;
- initial_sync_completed_at;
- initial_snapshot_todate;
- next_page;
- incremental_watermark;
- current_mode;
- last_checkpoint_at;
- last_seen_question_activity_at;
- total_questions_fetched;
- total_answers_fetched;
- total_documents_inserted;
- total_documents_updated;
- total_documents_unchanged;
- total_exact_duplicates;
- total_items_skipped;
- total_errors;
- last_job_id;
- state JSONB;
- created_at;
- updated_at.

Создай worker_instances:

- id UUID;
- name;
- instance_id unique;
- capabilities JSONB;
- version;
- hostname;
- pid;
- status;
- current_job_id nullable;
- started_at;
- heartbeat_at;
- stopped_at.

Создай job_events:

- id UUID;
- job_id FK;
- level;
- stage;
- code;
- message;
- metrics JSONB;
- created_at.

Создай ingestion_failures:

- id UUID;
- job_id FK;
- source_id FK;
- external_id nullable;
- entity_type;
- error_code;
- safe_message;
- retryable;
- attempt;
- context JSONB;
- created_at;
- resolved_at nullable.

Добавь необходимые indexes, check constraints и foreign keys.

Создай надёжные partial unique indexes либо эквивалентные constraints:

- одна активная SOURCE_SYNC job на source;
- одна активная DOCUMENT_REINDEX/DOCUMENT_REPROCESS job на document;
- одна активная FULL_REINDEX job.

Активные статусы: QUEUED и RUNNING.

Проверь upgrade, downgrade и повторный upgrade на disposable PostgreSQL.

==================================================
3. JOB TYPES И STATES
==================================================

Сохрани существующие job types и добавь при необходимости:

- SOURCE_SYNC;
- DOCUMENT_REPROCESS;
- DOCUMENT_REINDEX;
- FULL_REINDEX;
- HEALTH_CHECK.

Worker 5.1 должен обрабатывать:

- SOURCE_SYNC только в ограниченном fetch/checkpoint режиме до появления processing pipeline 5.2;
- DOCUMENT_REPROCESS может пока отклоняться безопасным типизированным кодом HANDLER_NOT_READY, если он ещё не создаётся через UI.

Не помечай SOURCE_SYNC COMPLETED, если данные не прошли обработку. В 5.1 допустим внутренний режим DRY_RUN/FETCH_ONLY для тестов клиента. Полный handler завершится в 5.2.

JobStatus:

- QUEUED;
- RUNNING;
- COMPLETED;
- FAILED;
- CANCELLED.

JobStage минимум:

- PREPARING;
- FETCHING_QUESTIONS;
- FETCHING_ANSWERS;
- WAITING_BACKOFF;
- PROCESSING;
- FINALIZING.

==================================================
4. ATOMIC JOB CLAIM
==================================================

Реализуй repository/service для atomic claim:

1. Найти QUEUED job поддерживаемого типа.
2. next_attempt_at IS NULL или <= now().
3. cancellation_requested_at IS NULL.
4. Заблокировать строку через SELECT ... FOR UPDATE SKIP LOCKED.
5. Установить RUNNING, claimed_by, claimed_at, lease_expires_at, heartbeat_at.
6. started_at установить только при первой попытке.
7. Увеличить attempt только при реальном новом запуске.
8. Commit claim transaction.
9. Выполнять job вне этой transaction.

Добавь integration test с двумя независимыми AsyncSession/worker attempts: одна job выдаётся только одному worker.

==================================================
5. LEASE, HEARTBEAT И STALE RECOVERY
==================================================

Добавь settings:

- WORKER_POLL_INTERVAL_SECONDS;
- WORKER_LEASE_SECONDS;
- WORKER_HEARTBEAT_SECONDS;
- WORKER_MAX_ATTEMPTS;
- WORKER_SHUTDOWN_TIMEOUT_SECONDS.

Разумные development defaults:

- poll: 2;
- lease: 60;
- heartbeat: 15;
- max attempts: 5.

Worker:

- регистрирует worker_instance;
- обновляет heartbeat;
- продлевает lease текущей job;
- корректно обрабатывает SIGTERM/SIGINT;
- перестаёт брать новые jobs при shutdown;
- пытается завершить безопасную точку текущей операции;
- отмечает worker_instance STOPPED.

Stale recovery:

- RUNNING job с истёкшим lease может быть восстановлена;
- если attempt < max_attempts, вернуть в QUEUED с next_attempt_at;
- если attempts исчерпаны, FAILED;
- записать job event;
- не сбрасывать checkpoint.

==================================================
6. CANCELLATION
==================================================

Существующий stop source endpoint должен устанавливать cancellation_requested_at, а не убивать process.

Worker проверяет cancellation:

- перед внешним запросом;
- после внешнего ответа;
- перед обработкой batch;
- перед сохранением следующего checkpoint;
- во время backoff/retry sleep.

При cancellation:

- завершённые ранее batches сохраняются;
- незавершённая transaction откатывается;
- checkpoint остаётся на последнем успешном commit;
- job становится CANCELLED;
- source перестаёт быть SYNCING;
- stop повторно вызывается идемпотентно.

==================================================
7. STACK EXCHANGE CLIENT
==================================================

Создай отдельный integration layer, например:

app/integrations/stackexchange/
  client.py
  schemas.py
  errors.py
  rate_limiter.py

Используй один httpx.AsyncClient на lifecycle worker.

Настройки:

- STACKEXCHANGE_API_BASE_URL=https://api.stackexchange.com/2.3;
- STACKEXCHANGE_SITE=ru.stackoverflow;
- STACKEXCHANGE_TAG=python;
- STACKEXCHANGE_KEY optional;
- STACKEXCHANGE_QUESTION_FILTER=withbody;
- STACKEXCHANGE_ANSWER_FILTER=withbody;
- STACKEXCHANGE_PAGE_SIZE=100;
- STACKEXCHANGE_REQUESTS_PER_SECOND=3;
- STACKEXCHANGE_CONNECT_TIMEOUT_SECONDS;
- STACKEXCHANGE_READ_TIMEOUT_SECONDS;
- STACKEXCHANGE_MAX_RETRIES;
- STACKEXCHANGE_QUOTA_RESERVE;
- STACKEXCHANGE_MAX_RESPONSE_BYTES;
- STACKEXCHANGE_USER_AGENT.

API key берётся только из environment.

Не сохраняй API key и не включай его в repr/error/log.

==================================================
8. API DTO
==================================================

Создай Pydantic DTO для common wrapper:

- items;
- has_more;
- quota_max;
- quota_remaining;
- backoff optional;
- error_id optional;
- error_name optional;
- error_message optional.

Question DTO поддерживает минимум:

- question_id;
- title;
- body;
- tags;
- link;
- owner optional;
- creation_date;
- last_activity_date;
- last_edit_date optional;
- score;
- view_count;
- answer_count;
- accepted_answer_id optional;
- is_answered;
- content_license optional.

Answer DTO:

- answer_id;
- question_id;
- body;
- owner optional;
- creation_date;
- last_activity_date;
- last_edit_date optional;
- score;
- is_accepted;
- content_license optional.

Optional API fields не делай обязательными без причины.

==================================================
9. QUESTIONS И ANSWERS REQUESTS
==================================================

Questions:

GET /questions

Параметры:

- site=ru.stackoverflow;
- tagged=python;
- page;
- pagesize <= 100;
- sort;
- order;
- fromdate optional;
- todate optional;
- filter;
- key только если настроен.

Answers:

GET /questions/{ids}/answers

- IDs разделяются точкой с запятой;
- не более 100 question IDs в одном request;
- answers endpoint также проходит pagination по has_more.

Не выполняй отдельный HTTP request для каждого вопроса.

==================================================
10. PAGINATION
==================================================

Создай async iterators/services:

- iterate_questions(...);
- fetch_answers_for_question_ids(...).

Они должны:

- следовать has_more;
- прекращать работу при empty items;
- иметь maxPages safety limit;
- проверять cancellation;
- обновлять request_count и bytes_received;
- выдавать страницы, а не загружать всё в память;
- корректно обрабатывать отсутствующий has_more как false.

==================================================
11. RATE LIMIT, BACKOFF И RETRIES
==================================================

Реализуй локальный async rate limiter с configurable requests/second.

Обязательно учитывать:

- wrapper.backoff: не вызывать тот же method до истечения указанного времени;
- HTTP Retry-After;
- timeout;
- connection error;
- 429;
- 502/503/504;
- ограниченный exponential backoff;
- jitter;
- max retries;
- cancellation во время ожидания.

Не повторяй бесконечно:

- 400;
- 401;
- 403;
- API validation errors.

Heartbeat должен продолжать обновляться во время долгого backoff.

Создавай job events для backoff/retry/quota-low, но не спамь событиями.

==================================================
12. QUOTA
==================================================

После каждого wrapper обновляй source:

- rate_limit_remaining/quota_remaining;
- rate_limit_total/quota_max;
- timestamp последнего обновления.

Если quota_remaining <= configured reserve:

- сохранить checkpoint;
- записать WARNING event;
- не выполнять tight loop;
- поставить job в QUEUED с next_attempt_at либо FAILED retryable по единой документированной логике;
- source должен показывать причину паузы.

Не выдумывай официальный quota reset time, если API его не вернул.

==================================================
13. SOURCE TEST CONNECTION
==================================================

Переведи endpoint test source на новый client.

Он выполняет один маленький request:

- tagged=python;
- pagesize 1–5;
- без сохранения documents;
- с timeout;
- с проверкой wrapper schema.

Возвращает:

- success;
- latency_ms;
- quota_remaining;
- quota_max;
- has_more;
- checked_at.

Создаёт audit event, но не SOURCE_SYNC job.

==================================================
14. SOURCE SYNC REQUEST
==================================================

Расширь POST /api/admin/sources/{sourceId}/sync.

Request:

- mode: AUTO | INITIAL | INCREMENTAL;
- max_documents optional;
- max_pages optional;
- dry_run optional.

На 5.1 dry_run=true должен быть полностью поддержан.

Правила:

- только ADMIN;
- source enabled;
- один active sync на source;
- max_documents и max_pages имеют безопасные maximum;
- endpoint только создаёт job;
- worker выполняет job;
- audit создаётся атомарно.

==================================================
15. CHECKPOINT 5.1
==================================================

Checkpoint minimum:

- mode;
- fixed_todate;
- current_page;
- answer_page_by_batch при необходимости;
- questions_fetched;
- answers_fetched;
- request_count;
- last_successful_page;
- last_event_at.

Checkpoint сохраняется после законченной безопасной единицы работы.

Нельзя продвигать checkpoint до успешного commit.

В 5.1 dry-run checkpoint может сохраняться без document inserts, но это должно быть явно отделено от production sync state, чтобы dry-run не сделал initial sync завершённым.

==================================================
16. JOB EVENTS API
==================================================

Добавь:

GET /api/admin/jobs/{jobId}/events
GET /api/editor/jobs/{jobId}/events

ADMIN видит все разрешённые события.

EDITOR видит read-only события jobs, к которым у него уже есть доступ.

Поддержи pagination и sort.

Не возвращай secrets или полный API response.

==================================================
17. SYSTEM STATUS
==================================================

System API должен определять worker status по worker_instances.heartbeat_at.

Статусы:

- ONLINE;
- DEGRADED;
- OFFLINE.

Crawler worker может стать ONLINE.

Qdrant, Ollama, BM25, HNSW, embedding и reranker остаются NOT_CONFIGURED/OFFLINE с честным сообщением.

==================================================
18. WORKER DOCKER SERVICE
==================================================

Расширь compose.yaml сервисом worker.

Требования:

- тот же backend image/build;
- команда python -m app.worker либо эквивалент;
- non-root;
- depends_on PostgreSQL health;
- environment из текущей схемы;
- restart policy для local development;
- корректный SIGTERM;
- не публиковать порт;
- не добавлять Redis/Celery.

Поддержи и docker compose, и имеющийся legacy docker-compose через документацию/Makefile detection, не дублируя compose files.

==================================================
19. TESTS 5.1
==================================================

Не удаляй существующие tests.

Добавь tests минимум:

Job queue:

1. Atomic claim выдаёт job одному worker.
2. SKIP LOCKED работает при двух claims.
3. Future next_attempt_at не захватывается.
4. Heartbeat продлевает lease.
5. Stale lease возвращает job в QUEUED.
6. Max attempts переводит в FAILED.
7. Cancellation переводит в CANCELLED.
8. Stop идемпотентен.
9. Partial unique constraint блокирует второй active SOURCE_SYNC.
10. Worker instance heartbeat сохраняется.

Stack Exchange client:

11. site=ru.stackoverflow.
12. tagged=python.
13. pagesize <= 100.
14. questions pagination следует has_more.
15. answer batch не более 100 IDs.
16. answers pagination следует has_more.
17. wrapper backoff соблюдается.
18. Retry-After соблюдается.
19. 429 retry ограничен.
20. 502/503 retry ограничен.
21. 400 не повторяется бесконечно.
22. quota обновляет source.
23. quota reserve останавливает загрузку.
24. cancellation прерывает backoff.
25. API key отсутствует в logs/events/errors.
26. response size limit работает.
27. test connection не сохраняет documents.

API/RBAC:

28. USER не запускает sync.
29. EDITOR не запускает sync.
30. ADMIN создаёт dry-run sync.
31. Второй active sync возвращает 409.
32. Job events защищены permissions.
33. HTTP response совместим с frontend adapter.

Все внешние HTTP-вызовы mock-ировать через MockTransport/respx.

==================================================
20. ДОКУМЕНТАЦИЯ 5.1
==================================================

Создай/обнови:

- docs/worker-architecture.md;
- docs/stackexchange-client.md;
- docs/stage5-ingestion.md;
- backend/README.md;
- docs/erd.md;
- docs/api-contract.md.

Опиши:

- claim;
- lease;
- heartbeat;
- stale recovery;
- cancellation;
- graceful shutdown;
- questions/answers pagination;
- quota/backoff;
- dry-run;
- почему full import не запускается автоматически.

==================================================
21. ПРОВЕРКИ И GIT
==================================================

Перед началом:

- git status;
- git branch --show-current;
- git log --oneline -10.

Не менять origin. Не выполнять push. Не делать reset истории.

Backend:

- ruff check .;
- ruff format --check .;
- mypy app;
- pytest --cov=app --cov-report=term-missing --cov-fail-under=80.

Frontend regression:

- npm run typecheck;
- npm run lint;
- npm run test;
- npm run build;
- npm run format:check.

Docker:

- compose config;
- build backend и worker;
- migrations;
- worker heartbeat smoke;
- mocked dry-run sync.

После успешных проверок создай промежуточный коммит:

Реализована инфраструктура парсера Stack Exchange

Не выполняй push.

В конце выведи полный отчёт, hash коммита и подтверждение чистого рабочего дерева.

Не называй весь Этап 5 завершённым. После этого будет подэтап 5.2.
```
