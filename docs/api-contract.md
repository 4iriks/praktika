# PyAnswer API contract

Base URL: `/api`. JSON fields используют camelCase, Python и PostgreSQL — snake_case.

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

Reindex только создаёт `QUEUED` job; indexer не запускается в HTTP request.

### ADMIN

- dashboard: `GET /admin/dashboard`;
- users: list/detail/role/block/unblock;
- sources: list/detail/update/test/sync/stop;
- jobs: list/detail/retry/cancel/full-reindex;
- audit: read-only list/detail;
- system: status/health-check/settings.

### Operations

- `GET /health/live` — без DB query;
- `GET /health/ready` — PostgreSQL readiness;
- `GET /status`, `GET /system/public-policy`;
- `GET /search` — HTTP 501 до Этапа 6;
- `POST /ask` — HTTP 501 до Этапа 6.

## 401 handling frontend

HTTP adapter сообщает AuthProvider о 401. Provider переводит auth state в anonymous и удаляет
только user/role-sensitive TanStack Query cache. Redirect выполняется route/auth flow, поэтому
глобального redirect loop нет. 403 сохраняется как typed `ApiError` и ведёт UI на доступный 403
scenario.
