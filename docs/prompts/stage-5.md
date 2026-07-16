# PyAnswer — исходное задание Этапа 5

Этот файл хранит нормализованную копию присланной части задания Этапа 5. Полученный в чате
фрагмент заканчивается в разделе «Сохранение кода» на примере fenced Python block; продолжение
спецификации следует дописать сюда после получения, не смешивая реализацию с Этапом 4.

## Предпосылки и границы

Этапы 1–4 должны быть реализованы и сохранены: React frontend, FastAPI/PostgreSQL/SQLAlchemy/
Alembic backend, Argon2id, opaque HttpOnly sessions, CSRF, USER/EDITOR/ADMIN server RBAC,
user/editor/admin API, models documents/answers/tags/sources/jobs/audit, mock+HTTP adapters,
compose PostgreSQL/backend и tests.

Фактический код — источник истины. Нельзя создавать параллельные дубли моделей или переписывать
frontend/backend. Аккуратно расширять существующие names/contracts с обратной совместимостью.

На Этапе 5 запрещены Qdrant, dense/sparse embeddings, BM25/HNSW/hybrid/fusion/reranker,
Ollama/LLM/RAG и fake SQL search. `/api/search` и `/api/ask` продолжают честно отдавать 501.

## Цель и корпус

Реализовать настоящий Stack Exchange API ingestion pipeline: questions с tag python,
batch answers, initial и incremental sync, pagination/checkpoint/resume, rate limit/backoff/retry,
HTML normalization с сохранением Python code, deterministic answer selection/dedup/versioning/
chunking, chunks в PostgreSQL, отдельный durable worker, job lifecycle/heartbeat/cancel/retry,
реальные данные editor/admin и подготовку к будущему Qdrant.

Источник: `ru.stackoverflow`, tag `python`, цель около 25 000 threads, обязательный минимум 5 000.
Accepted answer включается при наличии, плюс до 3 лучших non-accepted; без accepted — до 4 лучших.
Все ответы можно хранить, в canonical/chunks входят selected. Ожидается 70–100 тыс. chunks,
целевой объём до 30 ГБ при абсолютном лимите 35 ГБ.

## Durable PostgreSQL worker

- Отдельный Docker service `worker`, команда `python -m app.worker`, общий backend package и DB.
- Никаких FastAPI BackgroundTasks, frontend/React parsing, вечных API threads или работы внутри
  HTTP request.
- Worker atomically claims supported jobs через `SELECT FOR UPDATE SKIP LOCKED`, задаёт workerId,
  lease/heartbeat/progress/checkpoint, cancellation/retries/stale recovery/graceful SIGTERM.
- Одна job не выполняется двумя workers, progress не уменьшается, HTTP не держит DB transaction,
  shutdown не берёт новую job.
- Этап 5 полноценно выполняет `SOURCE_SYNC`; допустим честный `DOCUMENT_REPROCESS`. Нельзя называть
  preprocessing завершённым BM25/Vector reindex или ставить READY без индекса.

Jobs расширяются полями: `claimed_by`, `claimed_at`, `lease_expires_at`, `heartbeat_at`, `attempt`,
`max_attempts`, `next_attempt_at`, `cancellation_requested_at`, `checkpoint/result JSONB`,
`request_count`, `bytes_received`, optional planned duration, updated_at. Future queued job не
claim-ится. Partial unique constraints защищают active source sync/document process/full reindex.

Lease defaults около 60 s, heartbeat 10–15 s; recovery увеличивает attempt и requeues либо FAILED.
Environment: worker poll/lease/heartbeat/max attempts/shutdown timeout. Tests используют
управляемое время и корректный heartbeat lifecycle.

## Worker instances и events

`worker_instances`: id/name/instance_id/capabilities/version/start/heartbeat/current_job/hostname/
pid/status/stopped_at, capabilities `source_sync`, `document_reprocess`; никаких secrets/env dump.
System API определяет Crawler worker ONLINE/OFFLINE/DEGRADED по heartbeat, но Indexer/Qdrant/
Ollama остаются unavailable.

`job_events`: id/job/level/stage/code/message/metrics JSONB/created_at; levels DEBUG/INFO/WARNING/
ERROR. События: claim, sync mode start, fetched pages/batched answers/backoff/quota/checkpoint/
commit/insert/update/duplicate/skip/retry/cancel/complete/fail. Без секретов/full API payload и без
избыточного event на строки. Добавить `GET /api/admin/jobs/{jobId}/events`; EDITOR видит события
доступных jobs read-only.

## Source sync state и modes

Отдельная 1:1 `source_sync_state`:

- initial completion/snapshot todate/next page;
- incremental watermark/current mode/last checkpoint;
- last question activity/creation;
- counters fetched answers/questions, inserted/updated/unchanged/exact duplicates/skipped/errors;
- last job/state JSONB/timestamps.

Checkpoint продвигается только после commit соответствующего DB batch и обеспечивает resume после
manual stop/network error/worker или Docker restart/crash.

`SourceSyncMode`: AUTO/INITIAL/INCREMENTAL. AUTO выбирает INITIAL до завершения snapshot, затем
INCREMENTAL.

INITIAL: questions `sort=creation`, `order=desc`, fixed `todate`, tagged python, pagesize 100,
до target/has_more false/empty/cancel/quota/fatal. Fixed todate предотвращает смещение backfill.

INCREMENTAL: `sort=activity`, desc, fromdate от successful watermark с configurable overlap
(`STACKEXCHANGE_INCREMENTAL_OVERLAP_SECONDS`, dev 86400), fixed todate. Overlap безопасен через
dedup. Watermark меняется только после полного success.

## Stack Exchange typed client

Отдельный `app/integrations/stackexchange/client.py`, без SQLAlchemy. Один lifecycle
`httpx.AsyncClient` worker-а.

Environment: API base URL `https://api.stackexchange.com/2.3`, site/tag, optional key, question/
answer filters, page size, requests/s, connect/read/write/pool timeouts, max retries, quota reserve,
explicit PyAnswer User-Agent. Key нельзя хранить в source/job/audit/events/frontend/response/error;
source отдаёт только `apiKeyConfigured`.

Questions: `GET /questions` с site/tagged/page/pagesize/sort/order/fromdate optional/todate/filter/
optional key. Answers: `GET /questions/{ids}/answers`, до 100 IDs, IDs через `;`, вся pagination.

На каждой questions page: собрать IDs, пакетно получить все answer pages, сгруппировать, выбрать,
обработать docs, commit batch, затем checkpoint. Никакого request per question.

Typed wrapper: optional `items`, `has_more`, `quota_max`, `quota_remaining`, `backoff`, error fields.
После response обновлять source quota/job request and bytes; валидировать items, backoff/error.
Backoff event+wait блокирует повтор этого method, cancellation остаётся responsive, heartbeat жив.

## Rate limits, retries, quota и safety

Локальный async limiter по умолчанию 2–5 req/s. Учитывать Stack Exchange backoff и Retry-After,
exponential backoff+jitter, cancellation, max retries, временные timeout/connection/429/502/503/
504/some 5xx отдельно от permanent 400/401/403/validation. Никакого tight retry loop.

После каждого response сохранять quota remaining/max/last update. При quota <= reserve сохранить
checkpoint/event, requeue with nextAttemptAt либо retryable failure, источник показывает причину,
никаких бесконечных requests и выдуманного official quota reset.

Safety limits: response bytes/items, HTML/title/body size, answers/question, pages/job, manual smoke
documents. Oversize безопасно останавливается с sanitized error. Source config не позволяет
arbitrary API URL/site; allowlist предотвращает SSRF.

## Stack Exchange DTO

Question optional fields: question_id/title/body/tags/link/owner identifiers+name+link,
creation/last activity/last edit, score/views/answers, accepted id/is_answered, close fields,
content license. Raw DTO не идёт frontend.

Answer fields: answer_id/question_id/body/owner, timestamps, score/is_accepted/license.
Предпочтительно хранить все fetched answers и добавить `sanitized_html`, `body_hash`, `last_seen_at`,
`selected_for_corpus`, `selection_rank`, `source_missing`, `content_license`; unique document+
external id. Не удалять существующие IDs/relationships.

## Deterministic answer selection

Если accepted получен: accepted первый; остальные sort score DESC, зафиксированный creation order,
answerId ASC tie-breaker; выбрать до `maxAdditionalAnswers`. Без accepted — до
`maxAdditionalAnswers + 1`. Максимум 4. Если question заявляет accepted ID, но answer не получен,
warning/metric, не подменять другим, продолжить доступные. Обязательны unit tests.

## HTML и code

Нельзя чистить HTML regex. Использовать BeautifulSoup+lxml либо другой parser, при необходимости
bleach. Хранить ограниченный raw HTML только при необходимости, sanitized HTML, normalized plain
text и canonical Markdown/text. Raw HTML не рендерится без sanitization и не попадает в audit/log.
Удалять script/style/iframe/object/embed, dangerous attributes/event handlers/javascript URLs.

Очистка обязана сохранять whitespace/indentation/newlines, `pre/code`, inline code и Python special
characters. `<pre><code>…</code></pre>` превращается в fenced code block, например:

```python
def example():
    return True
```

## Статус сохранённого задания

Это последняя полностью полученная часть спецификации Этапа 5. Реализацию Этапа 5 начинать только
после отдельного завершения и коммита Этапа 4 и после сохранения недостающего продолжения prompt.
