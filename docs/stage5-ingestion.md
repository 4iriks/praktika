# PyAnswer — Этап 5, подэтап 5.1

Подэтап 5.1 создаёт инфраструктуру будущей загрузки Stack Overflow на русском. Он не завершает
весь Этап 5 и не запускает полный импорт корпуса.

## Реализуемая граница 5.1

- PostgreSQL-backed durable job queue;
- отдельный worker process;
- atomic claim через `FOR UPDATE SKIP LOCKED`;
- lease, heartbeat, stale recovery и graceful shutdown;
- cancellation, checkpoint, retry schedule и job events;
- типизированный Stack Exchange client;
- questions/answers pagination, rate limit, backoff и quota;
- source test connection;
- ограниченный `SOURCE_SYNC` dry-run/fetch-only flow;
- Docker worker service.

Полный production handler, HTML cleaning, answer selection, deduplication, revisions и chunks
будут добавлены в 5.2. На 5.1 dry-run не сохраняет documents и не завершает initial sync.

## Миграция

Ревизия `20260716_0002` следует за Stage 4 revision `20260715_0001`. Она расширяет `jobs`, делает
неизвестный Stack Exchange quota reset nullable, добавляет время quota update и создаёт:

- `source_sync_states`;
- `worker_instances`;
- `job_events`;
- `ingestion_failures`.

Миграция сохраняет существующие Stage 4 jobs и partial unique правила активных заданий.
Downgrade проверяется только на disposable PostgreSQL.

## Режимы sync

- `AUTO` выбирает initial, пока первоначальная загрузка не завершена, затем incremental;
- `INITIAL` использует `sort=creation`, descending order и фиксированный `todate`;
- `INCREMENTAL` использует `sort=activity`, watermark minus overlap и фиксированный `todate`.

В 5.1 полностью поддерживается безопасно ограниченный dry-run. Dry-run checkpoint изолирован от
production source state и не обновляет `initial_sync_completed_at` или incremental watermark.

Запрос создания job может включать `mode`, `maxDocuments`, `maxPages` и `dryRun`. Endpoint только
создаёт DB job; HTTP request не выполняет загрузку.

## Lifecycle SOURCE_SYNC

1. ADMIN создаёт job для enabled source.
2. Partial unique index блокирует вторую активную job.
3. Worker атомарно выполняет claim.
4. Клиент получает page questions и batch pages answers без открытой DB transaction.
5. Worker фиксирует counters/event/checkpoint безопасной единицей.
6. Cancellation или quota pause сохраняет последний успешный checkpoint.
7. Retry продолжает с checkpoint; stale lease восстанавливается ограниченно.

`COMPLETED` не означает созданный поисковый индекс. BM25/vector statuses не переводятся в READY.

## Запуск development окружения

Создайте `.env` из примера и задайте собственный PostgreSQL password. Stack Exchange key можно
оставить пустым.

```bash
make backend-migrate
make worker-up
make worker-health
make worker-logs
```

Для Compose V1 команда задаётся явно:

```bash
make COMPOSE=docker-compose worker-up
```

## Проверки

Обычные tests используют mocked HTTP. Проверяются atomic claim, competing workers, lease,
heartbeat, stale recovery, cancellation, partial unique indexes, pagination, batching до 100 ID,
backoff, Retry-After, quota reserve, response size и отсутствие key в диагностике.

Полный импорт 25 000 веток не является проверкой 5.1 и автоматически не запускается.

## Честные ограничения

- документы, revisions и chunks появятся в 5.2;
- worker не создаёт BM25/vector индекс;
- Qdrant, embeddings, HNSW, reranker и Ollama отсутствуют;
- `/api/search` и `/api/ask` в HTTP mode продолжают возвращать 501;
- mock frontend search продолжает работать независимо от ingestion.
