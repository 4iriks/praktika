# Worker PyAnswer — архитектура подэтапов 5.1–5.2

Подэтап 5.1 добавляет отдельный процесс `worker`, который использует тот же Python package и
PostgreSQL, что и FastAPI, но не обслуживает HTTP. Длительная работа не запускается через
FastAPI `BackgroundTasks`, frontend, неуправляемый thread или subprocess.

На 5.2 worker полноценно обрабатывает `SOURCE_SYNC`: сохраняет threads, revisions и chunks.
`DOCUMENT_REINDEX` и `FULL_REINDEX` не выдаются за выполненную поисковую индексацию.

## Компоненты

- `jobs` — durable очередь и состояние выполнения;
- `worker_instances` — зарегистрированные процессы и их heartbeat;
- `job_events` — безопасный технический журнал;
- `source_sync_states` — checkpoint и накопительные счётчики источника;
- `ingestion_failures` — изолированные безопасные ошибки ingestion;
- `worker` в `compose.yaml` — отдельный non-root процесс `python -m app.worker`.

Worker имеет capabilities `source_sync` и `document_reprocess`. Наличие capability не означает,
что поисковый indexer реализован.

## Атомарный claim

Worker выбирает только поддерживаемую `QUEUED` job, у которой `next_attempt_at` отсутствует или
уже наступил и cancellation ещё не запрошен. Claim выполняется короткой транзакцией:

1. `SELECT ... FOR UPDATE SKIP LOCKED` блокирует одну подходящую строку.
2. Job получает `RUNNING`, `claimed_by`, `claimed_at`, `lease_expires_at` и `heartbeat_at`.
3. `attempt` увеличивается только при новом фактическом запуске.
4. Транзакция фиксируется.
5. Сетевые запросы и ожидания выполняются уже без открытой DB transaction.

Partial unique indexes запрещают одновременно иметь две активные синхронизации одного source,
две активные reindex/reprocess job одного document и две активные `FULL_REINDEX`. Активными
считаются `QUEUED` и `RUNNING`.

## Lease, heartbeat и восстановление

По умолчанию lease действует 60 секунд, heartbeat обновляется каждые 15 секунд. Heartbeat:

- продлевает lease текущей job;
- обновляет `worker_instances.heartbeat_at`;
- не изменяет progress назад;
- имеет lifecycle, связанный с worker, и завершается вместе с ним.

`RUNNING` job с истёкшим lease считается stale. Recovery сохраняет checkpoint и либо возвращает
job в `QUEUED` с ограниченной следующей попыткой, либо переводит её в `FAILED`, если исчерпан
`max_attempts`. Событие recovery сохраняется в `job_events`.

## Checkpoint

Checkpoint хранит режим, фиксированный `todate`, страницу, item offset, counters и последнюю
успешную безопасную единицу. Он обновляется только после commit batch. Поэтому capped run,
restart worker или Docker не пропускает остаток уже полученной страницы.

Dry-run хранит checkpoint в job, но не помечает initial sync завершённым и не продвигает
production watermark.

## Cancellation и shutdown

API stop/cancel выставляет `cancellation_requested_at`; процесс не убивается принудительно.
Worker проверяет cancellation перед и после HTTP-запроса, перед обработкой/commit batch и во
время retry/backoff. Уже зафиксированные batches сохраняются, незавершённая транзакция
откатывается, job становится `CANCELLED` в безопасной точке.

При `SIGTERM`/`SIGINT` worker:

1. прекращает claim новых jobs;
2. запрашивает остановку текущего цикла;
3. завершает безопасную точку в пределах shutdown timeout;
4. переводит instance в `STOPPED`.

Compose использует init process и `stop_grace_period`, согласованный с
`WORKER_SHUTDOWN_TIMEOUT_SECONDS`.

## Транзакционные границы

Claim, heartbeat, checkpoint, terminal transition и запись событий используют короткие
транзакции. HTTP-запрос, rate-limit sleep и API backoff никогда не выполняются под row lock или
открытой транзакцией. Success state не фиксируется отдельно от соответствующих данных.

## Наблюдаемость и безопасность

`job_events` содержит stage, code, короткое сообщение и агрегированные metrics. В события,
checkpoint, result, failure context и логи не попадают API key, cookies, session/CSRF token,
полный API response и необработанный HTML.

System API определяет Crawler worker по свежести `worker_instances.heartbeat_at`. Qdrant,
Ollama, BM25, HNSW, embedding model, reranker и indexer остаются `NOT_CONFIGURED`/`OFFLINE`.

## Запуск

```bash
make backend-migrate
make worker-up
make worker-health
make worker-logs
```

Compose можно переопределить явно:

```bash
make COMPOSE=docker-compose worker-up
```

Полная загрузка 25 000 веток на подэтапе 5.2 автоматически не запускается.
