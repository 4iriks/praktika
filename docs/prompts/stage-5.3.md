# ПРОМТ 5.3 — API/UI интеграция, smoke-import, документация и приёмка Этапа 5

```text
Продолжай разработку существующего проекта PyAnswer после завершения подэтапов 5.1 и 5.2.

Это заключительный подэтап 5.3 Этапа 5.

Сначала изучи фактические результаты:

- worker и job queue;
- Stack Exchange client;
- source sync state;
- cleaner;
- answer selection;
- canonicalization;
- hashing/dedup;
- revisions;
- chunks;
- real SOURCE_SYNC handler;
- API и tests;
- последние Git-коммиты.

Запусти текущие проверки до изменений.

==================================================
ЦЕЛЬ ПОДЭТАПА 5.3
==================================================

1. Полностью подключить ingestion к editor/admin frontend.
2. Довести source, jobs, system и documents pages.
3. Добавить operational API и отчёты.
4. Завершить Docker/Make/CLI.
5. Добавить capped live smoke, выключенный по умолчанию.
6. Провести полную regression-проверку.
7. Завершить документацию и ERD.
8. Зафиксировать Этап 5 как завершённый.

Не подключай Qdrant, BM25, HNSW, embeddings, reranker или Ollama. Это Этап 6.

Не запускать полный импорт 25 000 автоматически.

==================================================
1. FRONTEND API TYPES
==================================================

Расширь существующие типы без дублирования:

- SourceSyncMode;
- SourceSyncRequest;
- SourceSyncState;
- IngestionStats;
- IngestionFailure;
- JobEvent;
- ProcessingStatus;
- DeduplicationStatus;
- DocumentChunkSummary;
- WorkerStatus;
- IngestionJobResult.

Mock adapter и HTTP adapter должны поддерживать одинаковый interface.

Не вызывать fetch из pages/components.

Unsafe HTTP requests используют текущий CSRF механизм.

==================================================
2. ADMIN SOURCE PAGE
==================================================

/admin/sources в HTTP mode показывает реальные данные:

- source status;
- documents count / target;
- sync mode;
- initial sync complete;
- incremental watermark;
- current page/checkpoint;
- current job;
- questions fetched;
- answers fetched;
- inserted;
- updated;
- unchanged;
- duplicates;
- skipped;
- errors;
- chunks created;
- API requests;
- bytes received;
- quota remaining/max;
- last successful sync;
- worker availability.

Действия:

- test connection;
- start AUTO;
- start capped INITIAL smoke;
- start INCREMENTAL;
- stop current sync;
- open job;
- refresh.

Start dialog:

- mode;
- max documents;
- max pages;
- dry run;
- предупреждение, что полный импорт может занять время и quota.

Не предлагай одной обычной кнопкой автоматически импортировать 25 000 без подтверждения.

==================================================
3. JOB DETAILS И EVENTS
==================================================

/admin/jobs и /editor/jobs:

- показывают real job stage/progress;
- checkpoint;
- attempt/max attempts;
- lease/heartbeat;
- cancellation requested;
- request count;
- bytes received;
- result counters;
- error;
- retry time;
- связанный source/document;
- events timeline.

Auto-refresh только при QUEUED/RUNNING.

Не создавать бесконтрольные intervals; использовать TanStack Query refetchInterval с остановкой.

EDITOR остаётся read-only согласно permissions.

==================================================
4. EDITOR DOCUMENTS
==================================================

/editor/documents и detail должны показывать реальные поля:

- processing status;
- deduplication status;
- duplicateOf;
- content hash;
- metadata hash;
- version;
- selected answers count;
- chunks count;
- source updated at;
- last seen at;
- BM25/vector statuses NOT_INDEXED/OUTDATED;
- revisions summary;
- chunk summary.

Добавь read-only вкладки/блоки:

- выбранные ответы;
- чанки;
- revisions;
- ingestion failures для документа.

Не показывать raw unsanitized HTML.

==================================================
5. SYSTEM PAGE
==================================================

/admin/system должен показывать настоящие доступные данные:

- FastAPI;
- PostgreSQL;
- Crawler worker heartbeat;
- documents count;
- answers count;
- chunks count;
- revisions count;
- failures count;
- PostgreSQL estimated size;
- current active jobs;
- last ingestion activity.

Qdrant, Ollama, indexer, BM25, HNSW, embeddings и reranker честно показываются NOT_CONFIGURED/OFFLINE.

Не показывай их ONLINE.

==================================================
6. OPERATIONAL API
==================================================

Заверши endpoints:

GET /api/admin/sources/{sourceId}/sync-state
GET /api/admin/jobs/{jobId}/events
GET /api/editor/jobs/{jobId}/events
GET /api/admin/ingestion/stats
GET /api/admin/ingestion/failures
GET /api/admin/ingestion/failures/{failureId}

При необходимости добавь:

GET /api/editor/documents/{documentId}/chunks
GET /api/editor/documents/{documentId}/revisions

Поддержи pagination, filters и permission checks.

==================================================
7. CLI И MAKEFILE
==================================================

Добавь/обнови команды:

- make worker-up;
- make worker-logs;
- make worker-health;
- make sync-smoke;
- make sync-incremental;
- make ingestion-report.

Учти наличие legacy docker-compose. Сделай compose command configurable либо автоопределяемым.

Добавь scripts:

python -m app.scripts.enqueue_sync
python -m app.scripts.ingestion_report
python -m app.scripts.worker_health

enqueue_sync:

- source ID обязателен;
- mode;
- max documents/pages;
- dry-run;
- не запускает full import случайно;
- выводит job ID;
- использует business layer и audit либо явно документированный trusted local admin mode.

==================================================
8. LIVE SMOKE
==================================================

Автоматические tests не зависят от интернета.

Создай opt-in live smoke:

RUN_LIVE_STACKEXCHANGE_SMOKE=1

Ограничения:

- максимум 1–2 question pages;
- максимум 100–200 documents;
- не запускается pytest по умолчанию;
- не запускается Docker build/migration/seed;
- API key не печатается;
- quota выводится;
- результат отчётливо помечается LIVE.

Если env flag отсутствует, test должен быть корректно deselected/skipped только как opt-in integration test, а не как обязательный тест. Не использовать skip для обязательного поведения.

Полный import 25 000 не запускать.

==================================================
9. FULL IMPORT RUNBOOK
==================================================

Создай отдельную инструкцию, но не выполняй импорт автоматически.

Инструкция должна содержать:

1. Backup PostgreSQL.
2. Проверку свободного диска.
3. Worker health.
4. Source test.
5. Smoke sync 100 документов.
6. Проверку документов/answers/chunks.
7. Запуск AUTO/INITIAL без искусственного small limit.
8. Мониторинг quota/progress/events.
9. Stop/cancel.
10. Resume.
11. Incremental sync.
12. Проверку достижения минимум 5 000 документов.
13. Целевой объём около 25 000.

Добавь отдельную команду с явно опасным названием, например:

make sync-full-confirmed

Она должна требовать environment confirmation:

CONFIRM_FULL_SYNC=YES

Без него завершаться без запуска.

==================================================
10. FRONTEND TESTS
==================================================

Добавь tests минимум:

1. Source page отображает real sync state.
2. Start sync отправляет mode и limits.
3. Stop требует confirmation.
4. Job details показывает events.
5. Quota отображается.
6. Worker OFFLINE отображается честно.
7. Qdrant/Ollama не ONLINE.
8. Document показывает processing/dedup status.
9. Duplicate badge/link работает.
10. Chunks/revisions отображаются read-only.
11. HTTP error безопасно отображается.
12. Mock mode продолжает работать.
13. HTTP mode использует ingestion endpoints.
14. Auto-refresh останавливается после terminal status.

==================================================
11. BACKEND FINAL TESTS
==================================================

Добавь/проверь:

- operational endpoint permissions;
- pagination/filtering job events/failures;
- system worker online/offline;
- counts документов/answers/chunks;
- source stats;
- live smoke deselected by default;
- CLI не запускает full sync без confirmation;
- worker Docker graceful shutdown;
- no secret leakage;
- search/ask всё ещё 501.

Backend coverage не ниже 80%.

==================================================
12. ДОКУМЕНТАЦИЯ
==================================================

Создай/обнови:

- docs/stage5-ingestion.md;
- docs/stackexchange-client.md;
- docs/worker-architecture.md;
- docs/content-cleaning.md;
- docs/chunking.md;
- docs/ingestion-runbook.md;
- docs/erd.md;
- docs/sql_examples.sql;
- docs/api-contract.md;
- backend/README.md;
- frontend/README.md;
- корневой README.md.

docs/sql_examples.sql должен содержать работающие запросы:

1. Documents по source.
2. Answers по document.
3. Chunks по document.
4. Processing statuses.
5. Dedup statuses.
6. Documents без chunks.
7. OUTDATED/NOT_INDEXED.
8. Последняя успешная sync.
9. Job progress/events.
10. Ingestion failure rate.
11. Average chunks/document.
12. Popular tags.
13. Documents changed after indexing.
14. Exact duplicates.
15. Worker heartbeat.

Используй JOIN, GROUP BY, CTE, подзапрос и хотя бы одну полезную оконную функцию.

==================================================
13. ERD
==================================================

ERD должен соответствовать фактической БД и включать:

- sources;
- source_sync_states;
- jobs;
- job_events;
- worker_instances;
- documents;
- answers;
- tags/document_tags;
- document_revisions;
- document_chunks;
- ingestion_failures;
- duplicate self-reference;
- retry self-reference.

==================================================
14. FINAL CHECKS
==================================================

Backend:

- ruff check .;
- ruff format --check .;
- mypy app;
- pytest --cov=app --cov-report=term-missing --cov-fail-under=80.

Migrations на disposable PostgreSQL:

- Stage 4 → latest;
- downgrade только новых Stage 5 migrations;
- repeated upgrade;
- alembic check.

Frontend:

- npm run typecheck;
- npm run lint;
- npm run test;
- npm run build;
- npm run format:check.

Docker:

- compose config;
- build backend/worker/frontend;
- postgres up;
- migrations/bootstrap/seed;
- backend/worker up;
- health live/ready;
- worker heartbeat;
- mocked smoke SOURCE_SYNC;
- graceful worker stop.

Дополнительно проверить:

- нет TODO/FIXME;
- нет обязательных skipped tests;
- нет API key/secrets;
- нет SQLite;
- нет network calls в обычных tests;
- нет transaction во время network wait;
- одна job не выполняется двумя workers;
- checkpoint только после commit;
- cancellation сохраняет completed batches;
- retry ограничен;
- backoff соблюдается;
- answer IDs batch <=100;
- code indentation сохраняется;
- XSS удаляется;
- content hash стабилен;
- chunks детерминированы;
- exact duplicates не удаляются;
- index statuses не READY;
- search/ask не выданы за готовые;
- mock frontend mode сохранён.

==================================================
15. GIT И ФИНАЛЬНЫЙ КОММИТ
==================================================

Не менять origin. Не выполнять push. Не переписывать историю.

После всех проверок создай финальный коммит Этапа 5:

Завершён пятый этап: парсер Stack Exchange и подготовка корпуса

Если в 5.1 и 5.2 уже были промежуточные коммиты, этот коммит содержит интеграцию и финальные правки, не squash предыдущих без необходимости.

Рабочее дерево в конце чистое.

==================================================
16. ФИНАЛЬНЫЙ ОТЧЁТ
==================================================

Выведи:

1. Краткое описание Этапа 5.
2. Все migrations и новые таблицы.
3. Расширенные таблицы.
4. Stack Exchange client.
5. Questions pagination.
6. Answer batching/pagination.
7. has_more/backoff/quota/retries.
8. Initial/incremental sync.
9. Checkpoint/resume/cancellation.
10. Worker claim/lease/heartbeat/stale recovery.
11. HTML cleaning/code preservation.
12. Answer selection.
13. Canonical document/hashes.
14. Dedup/revisions/chunks.
15. Frontend integration.
16. Docker/CLI/Make commands.
17. Документацию.
18. Backend test files/tests/coverage.
19. Frontend test files/tests.
20. Все результаты проверок.
21. Live smoke: выполнен или НЕ ВЫПОЛНЕН с причиной.
22. Количество imported documents в live smoke, если был.
23. Hash финального коммита.
24. Push не выполнялся.
25. Рабочее дерево чистое.
26. Известные ограничения.

Этап 5 считается завершённым только если:

- реальный Stack Exchange client существует;
- questions/answers pagination работает;
- has_more/backoff/quota соблюдаются;
- worker отдельный и durable;
- checkpoint/resume/cancellation работают;
- documents, answers, tags и chunks сохраняются в PostgreSQL;
- HTML очищается и код сохраняется;
- answer selection детерминирован;
- content hash стабилен;
- импорт идемпотентен;
- exact duplicate распознаётся;
- revisions/chunks работают;
- UI показывает настоящий ingestion progress;
- автоматические tests не зависят от интернета;
- Qdrant/Ollama/search/RAG ещё честно не реализованы;
- все проверки проходят;
- push не выполнен;
- рабочее дерево чистое.
```
