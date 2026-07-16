# PyAnswer API contract

Base URL: `/api`. JSON fields используют camelCase, Python и PostgreSQL — snake_case.

## Search 6.2

`GET /api/search` поддерживает `bm25`, `vector` и `hybrid`. Raw BM25/cosine scores возвращаются
раздельно; hybrid объединяет ranks через weighted RRF. Отсутствующий component или fallback
reranker обозначается `null`. Ответ содержит matched chunks, index version, timings и
`totalIsExact=false`, потому что pagination ограничена candidate window. Недоступность
Qdrant/model/обязательного reranker возвращает 503 в общем error envelope. `/api/ask` остаётся
501 до 6.3.

Подэтапы 5.1–5.2 расширяют существующий контракт operational-полями worker и ingestion. Старые
auth/user/editor/admin методы сохраняют обратную совместимость.

## Cookie и CSRF flow

1. `GET /auth/csrf` возвращает `{ "csrfToken": "..." }` и readable CSRF-cookie.
2. `POST /auth/login` или register отправляет тот же token в `X-CSRF-Token` и cookie.
3. Backend устанавливает opaque session reference как HttpOnly-cookie и ротирует CSRF.
4. Все POST/PUT/PATCH/DELETE требуют новый `X-CSRF-Token`.
5. Frontend HTTP adapter использует `credentials: "include"`, при `CSRF_INVALID` получает новый
   token и повторяет mutation ровно один раз.
6. Bearer/access token и browser token storage отсутствуют.

## Error envelope

```json
{
  "error": {
    "code": "FORBIDDEN",
    "message": "Недостаточно прав",
    "details": {},
    "requestId": "request-uuid"
  }
}
```

Коды: `BAD_REQUEST`, `UNAUTHORIZED`, `FORBIDDEN`, `CSRF_INVALID`, `NOT_FOUND`, `CONFLICT`,
`VALIDATION_ERROR`, `RATE_LIMITED`, `INTERNAL_ERROR`, `SERVICE_UNAVAILABLE`,
`SEARCH_ENGINE_NOT_READY`, `RAG_ENGINE_NOT_READY`.

## Pagination

```json
{
  "items": [],
  "pagination": {
    "page": 1,
    "pageSize": 20,
    "total": 100,
    "totalPages": 5
  }
}
```

Page начинается с 1, limit/page_size ограничен. Sort values закрыты allowlist; ORM использует
bound parameters и стабильный secondary sort по ID.

## Routes

### Auth и USER

- `GET /auth/csrf`;
- `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`;
- `GET/PATCH /users/me`, `GET /users/me/stats`;
- `GET/DELETE /history`, `DELETE /history/{historyId}`;
- `GET /saved`, `POST/DELETE /saved/{documentId}`;
- `POST /feedback`, `GET /feedback/by-response/{responseId}`,
  `DELETE /feedback/{feedbackId}`;
- `GET /documents/{documentId}`.

User endpoints никогда не открывают данные другого пользователя, даже ADMIN.

### EDITOR

- `GET /editor/dashboard`;
- `GET /editor/documents`, `GET /editor/documents/{documentId}`;
- `PATCH /editor/documents/{documentId}/metadata`;
- `POST /editor/documents/{documentId}/hide|restore|reindex`;
- `POST /editor/documents/bulk`;
- `GET /editor/jobs`.
- `GET /editor/jobs/{jobId}/events` — read-only события доступной job.

Reindex только создаёт `QUEUED` job; indexer не запускается в HTTP request.

### ADMIN

- dashboard: `GET /admin/dashboard`;
- users: list/detail/role/block/unblock;
- sources: list/detail/update/test/sync/stop;
- jobs: list/detail/retry/cancel/full-reindex;
- audit: read-only list/detail;
- system: status/health-check/settings.

### Ingestion 5.2

- `POST /admin/sources/{sourceId}/test` выполняет один малый Stack Exchange request и не создаёт
  job или document;
- `POST /admin/sources/{sourceId}/sync` только создаёт durable `SOURCE_SYNC` job;
- `POST /admin/sources/{sourceId}/stop` идемпотентно запрашивает cancellation, не убивая worker;
- `GET /admin/jobs/{jobId}/events` возвращает безопасную timeline событий.
- `GET /admin/sources/{sourceId}/sync-state` возвращает durable counters/checkpoint;
- `GET /admin/ingestion/stats` возвращает SQL aggregates документов, ответов, chunks/revisions;
- `GET /admin/ingestion/failures` и `/{failureId}` возвращают только sanitized diagnostics.
- `GET /editor/documents/{documentId}/chunks` возвращает очищенные read-only chunks;
- `GET /editor/documents/{documentId}/revisions` возвращает безопасные snapshots revisions;
- `GET /editor/documents/{documentId}/failures` возвращает sanitized diagnostics документа.

Пример тела start sync:

```json
{
  "mode": "AUTO",
  "maxDocuments": 100,
  "maxPages": 2,
  "dryRun": true
}
```

`mode` принимает `AUTO`, `INITIAL` или `INCREMENTAL`. Limits имеют серверные maximum. Поля можно
опустить для configured source defaults, но полный import не запускается автоматически.
`dryRun=true` выполняет fetch/checkpoint без сохранения documents и без завершения initial sync.
При `dryRun=false` worker сохраняет threads; capped run сохраняет page/item offset и не объявляет
snapshot завершённым, если остались элементы.

Job response сохраняет прежние поля и дополнительно может содержать:

- `claimedBy`, `claimedAt`, `leaseExpiresAt`, `heartbeatAt`;
- `attempt`, `maxAttempts`, `nextAttemptAt`;
- `cancellationRequestedAt`, `checkpoint`, `result`;
- `requestCount`, `bytesReceived`.

Job event содержит `id`, `jobId`, `level`, `stage`, `code`, `message`, безопасные `metrics` и
`createdAt`. Список использует общий pagination contract и стабильную сортировку.

Test connection возвращает `success`, `latencyMs`, quota remaining/max, `hasMore` и `checkedAt`.
API key, raw wrapper и response body не возвращаются.

### Operations

- `GET /health/live` — без DB query;
- `GET /health/ready` — PostgreSQL readiness;
- `GET /status`, `GET /system/public-policy`;
- `GET /search` — HTTP 501 до Этапа 6;
- `POST /ask` — HTTP 501 до Этапа 6.

Worker не меняет контракт search/ask: ingestion и поисковая индексация являются разными
этапами. `SOURCE_SYNC` на 5.2 не устанавливает BM25/vector status в `READY`.

## 401 handling frontend

HTTP adapter сообщает AuthProvider о 401. Provider переводит auth state в anonymous и удаляет
только user/role-sensitive TanStack Query cache. Redirect выполняется route/auth flow, поэтому
глобального redirect loop нет. 403 сохраняется как typed `ApiError` и ведёт UI на доступный 403
scenario.
# Search index API (Stage 6.1)

ADMIN endpoints: `GET /api/admin/indexes`, `/{id}`, `/active`, `/stats`; `POST /full-reindex`, `/{id}/validate`, `/cleanup`. Mutations используют текущие HttpOnly session + CSRF и возвращают существующий `BackgroundJob` contract. USER/EDITOR получают 403. Search/ask до 6.2/6.3 по-прежнему возвращают 501.
