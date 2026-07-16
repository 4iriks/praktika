# PyAnswer frontend

При `VITE_USE_MOCKS=false` страница поиска использует настоящий FastAPI `/api/search` с режимами
BM25, vector и hybrid, отменой через AbortSignal, nullable component scores, reranker fallback и
index/timing diagnostics. При `VITE_USE_MOCKS=true` прежний полностью локальный demo остаётся без
изменений. RAG в HTTP mode будет подключён в части 6.3.

PyAnswer — локальная интеллектуальная поисковая система по синтетической русскоязычной базе
вопросов и ответов о Python. Текущий frontend объединяет три законченных контура:

- пользовательский: регистрация → вход → поиск/RAG → история → saved → feedback → профиль;
- редакторский: документы → metadata/moderation → reindex → jobs;
- административный: users → sources → jobs → audit → system/settings.

Frontend Этапа 3 сохраняет полноценный mock-режим. На Этапе 4 в репозитории добавлены FastAPI и
PostgreSQL: при `VITE_USE_MOCKS=false` тот же типизированный adapter использует серверные auth,
user, editor и admin API. Qdrant, Ollama, crawler и настоящий indexer пока не реализованы.

## Стек

- React 18, TypeScript strict, Vite и React Router;
- TanStack Query для server-like состояния и точечной invalidation;
- Tailwind CSS, Lucide React, Sonner и Recharts;
- React Markdown, remark-gfm и react-syntax-highlighter;
- Vitest, Testing Library, ESLint и Prettier;
- production multi-stage Docker image с nginx.

Требуются Node.js 18+ и npm 9+.

## Запуск и проверки

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Vite запускает приложение на `http://localhost:5173`.

```bash
npm run typecheck
npm run lint
npm run test
npm run build
npm run format:check
```

## Демонстрация ролей

При `VITE_USE_MOCKS=true` seed идемпотентно создаёт три аккаунта:

| Роль   | Email                 | Пароль   |
| ------ | --------------------- | -------- |
| USER   | user@pyanswer.local   | Demo123! |
| EDITOR | editor@pyanswer.local | Demo123! |
| ADMIN  | admin@pyanswer.local  | Demo123! |

Дополнительно создаются 10 синтетических пользователей с разными ролями, статусами, датами и
персональной статистикой. Для проверки другой роли нужно выйти и войти под соответствующим
аккаунтом: role switcher намеренно отсутствует. Регистрация всегда создаёт только `USER`.

## Маршруты

Публичные и пользовательские:

- `/` — Spotlight-поиск;
- `/search` — документы или mock RAG с URL-состоянием;
- `/documents/:documentId` — публичное представление документа;
- `/login`, `/register` — mock-auth с безопасным `returnTo`;
- `/profile`, `/history`, `/saved` — защищённые пользовательские страницы;
- `/403` и `*` — доступ запрещён и 404.

EDITOR routes (ADMIN также имеет доступ):

- `/editor` — dashboard редактора;
- `/editor/documents` — URL-фильтруемый список документов и bulk actions;
- `/editor/documents/:documentId` — оригинал, управленческие metadata, audit и jobs;
- `/editor/jobs` — доступные редактору фоновые задания.

ADMIN routes:

- `/admin` — KPI и три содержательных графика;
- `/admin/users` — роли, блокировка и user details;
- `/admin/sources` — source configuration и sync;
- `/admin/jobs` — полный lifecycle jobs;
- `/admin/audit` — неизменяемый журнал аудита;
- `/admin/system` — mock telemetry и system settings.

Гость на защищённом route перенаправляется на `/login` с внутренним `returnTo`. Пути внешнего
домена и protocol-relative значения `//host` отклоняются. Авторизованный пользователь без права
получает `/403`, без redirect loop и без краткого отображения закрытой страницы.

## RBAC и permission matrix

Центральная matrix находится в `src/features/auth/permissions.ts`. UI использует
`hasPermission`, `hasAnyPermission`, `hasAllPermissions` и `usePermissions`; mock API повторно
проверяет permission и получает actor только из активной сессии.

| Группа | Permissions                                                                                                                                      |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| USER   | `SEARCH_USE`, `RAG_USE`, `PROFILE_MANAGE`, `HISTORY_MANAGE`, `SAVED_MANAGE`                                                                      |
| EDITOR | все USER + `EDITOR_ACCESS`, `MANAGED_DOCUMENTS_VIEW`, `DOCUMENT_METADATA_EDIT`, `DOCUMENT_STATUS_CHANGE`, `DOCUMENT_REINDEX`, `EDITOR_JOBS_VIEW` |
| ADMIN  | все USER и EDITOR + `ADMIN_ACCESS`, `USERS_MANAGE`, `SOURCES_MANAGE`, `ADMIN_JOBS_MANAGE`, `AUDIT_VIEW`, `SYSTEM_VIEW`, `SYSTEM_SETTINGS_MANAGE` |

Скрытие navigation — только UX. Прямой запрещённый вызов mock API возвращает единый `ApiError` с
`status=403`, `code=FORBIDDEN`, `message` и опциональными `details`. HTTP adapter ожидает тот же
формат для 400/401/403/404/409/422/500.

Frontend RBAC не является production-защитой. Реализованный FastAPI заново аутентифицирует actor
по server-side session и проверяет каждое permission, не доверяя роли, URL или payload браузера.

## Mock credentials, сессия и migration

Storage adapter расположен только в `src/mocks`; UI не обращается к `localStorage` или
`sessionStorage` напрямую. Текущий namespace — `pyanswer:mock:v2:*`.

- credentials содержат случайную salt и browser-side SHA digest, но не открытый пароль;
- `User` и admin responses не содержат password, salt, digest или session reference;
- session хранит только `userId`, `expiresAt`, `mockSessionVersion`;
- remember-session хранится в `localStorage`, короткая session — в `sessionStorage`;
- `accountVersion` повышается при role/status change и инвалидирует старую session;
- `BLOCKED` не может войти или восстановить старую session, данные пользователя сохраняются;
- seed не удаляет зарегистрированных пользователей и изолированные history/saved/feedback;
- миграция копирует корректные v1 records, добавляет безопасные defaults и только после успешного
  Stage 3 seed переключает schema marker;
- повреждённые JSON records удаляются точечно и не ломают приложение;
- `localStorage.clear()` не используется.

Browser-side digest — только демонстрационный механизм. Production-аутентификация должна быть
реализована FastAPI + Argon2 на сервере и защищённой `HttpOnly`, `Secure`, `SameSite` cookie.
Bearer token и access token в browser storage не используются.

Для локального сброса удалите ключи с префиксом `pyanswer:mock:` в DevTools → Application. Это
удалит только mock-данные текущего origin.

## Управление документами

Исходный массив публикаций остаётся единым. Repository хранит только управленческие metadata и
на чтении объединяет их с оригинальным вопросом/ответами.

`DocumentStatus`: `ACTIVE`, `HIDDEN`, `PENDING`, `FAILED`, `OUTDATED`.

`IndexStatus`: `READY`, `PENDING`, `FAILED`, `NOT_INDEXED`, `OUTDATED`.

EDITOR меняет только `normalizedTitle`, `managedTags` и `editorialNote`; tags приводятся к lowercase,
trim, удаляются пустые значения и дубли. Оригинальные URL, автор, тексты, даты и ID не меняются.
Сохранение повышает version, фиксирует actor/time и создаёт audit event.

- `ACTIVE` и `OUTDATED` участвуют в публичном поиске/RAG;
- `HIDDEN`, `PENDING`, `FAILED` исключены из поиска и источников RAG;
- публичная ссылка на недоступный документ не раскрывает его содержимое;
- hide требует причины, restore возвращает материал в публичный контур;
- reindex переводит индексы в `PENDING` и создаёт одно активное `DOCUMENT_REINDEX` job;
- bulk hide/restore/reindex принимает до 100 ID, защищён от double submit и возвращает success,
  skipped, failed по каждому документу с общим `batchId` и одним audit batch;
- физическое удаление документов отсутствует.

## Job engine

`JobType`: `SOURCE_SYNC`, `DOCUMENT_REINDEX`, `FULL_REINDEX`, `HEALTH_CHECK`.

`JobStatus`: `QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`.

Job progress, stage, processedItems и finishedAt вычисляются детерминированно из `startedAt`,
`plannedDurationMs` и текущего времени при чтении repository. Глобальных бесконечных timers нет;
UI refetch включён только пока присутствует активный job, его можно остановить и обновить вручную.
Tests используют fake timers.

EDITOR только просматривает свои допустимые jobs. ADMIN может отменить cancellable queued/running,
повторить failed/cancelled с `retryOfJobId` и запустить единственный активный `FULL_REINDEX`.

## Пользователи и источники

Только ADMIN управляет пользователями. API запрещает self-role-change, self-block и операции,
которые могли бы оставить систему без активного ADMIN. Role/status change повышает accountVersion
и создаёт audit event. Credential records не возвращаются таблице или detail drawer.

Основной source:

- `Stack Overflow на русском`, `STACK_EXCHANGE`;
- `https://ru.stackoverflow.com`, site `ru.stackoverflow`, tag `python`;
- target 25 000 документов, до 3 дополнительных ответов, page size 100.

ADMIN меняет ограниченные numeric settings и enabled-state, выполняет mock connection test,
запускает/останавливает единственный source sync. Реальный Stack Exchange API key не требуется и
не хранится; `apiKeyConfigured` — только синтетический флаг.

## Audit, system status и settings

Audit создаётся внутри repository вместе с бизнес-операцией, а не отдельным вызовом UI. Событие
содержит actor, action, entity, outcome, requestId, batchId и безопасные before/after/metadata.
Пароли, digest, salt, session references, tokens и secrets не записываются. UI не предоставляет
редактирование или удаление audit; diff отображается через безопасный JSON, без
`dangerouslySetInnerHTML`.

System page показывает только синтетические сервисы и конфигурацию Ubuntu / i5-13400F / 32 ГБ /
RTX 3080 Ti 12 ГБ / лимит 35 ГБ. Браузер не читает реальные hardware metrics. Health check
обновляет timestamp, создаёт job и audit event.

System settings:

- `searchCandidatesLimit`, `rerankerLimit`, `ragSourcesLimit`;
- `defaultMinimumConfidence`;
- `allowGuestSearch`, `allowGuestRag`;
- `historyRetentionDays`, `auditRetentionDays`.

Mock API реально применяет `allowGuestSearch`, `allowGuestRag` и `ragSourcesLimit`. Изменения
валидируются, подтверждаются, сохраняются через API и логируются.

## Архитектура и cache

```text
src/
  api/                 общий ApiClient, HTTP/mock adapters, ApiError, query keys/cache
  app/                 providers и Error Boundary
  components/
    layout/            публичная navigation
    management/        management UI и dialogs
    ui/                базовые компоненты
  features/
    auth/              session, permission matrix, guards
    documents/ rag/ search/
  layouts/             WorkspaceLayout и ManagementLayout
  mocks/               v2 storage, auth repository, management repository, audit, job engine
  pages/
    admin/ editor/ management/
  routes/              lazy routes и guards
  types/               публичные closed-union contracts
  utils/               URL state, validation, formatting
```

Query key factories разделяют public/user/editor/admin server state. После document mutation
точечно обновляются editor/admin dashboards, list/detail, public search/document, saved и audit.
После source mutation обновляются source/jobs/dashboard/audit. Logout и смена пользователя удаляют
только user/role-sensitive roots, поэтому admin cache не показывается следующему USER.

Основные типы Этапа 3: `Permission`, `PermissionMap`, `DocumentStatus`, `IndexStatus`,
`ManagedDocument`, `ManagedDocumentFilters`, `ManagedDocumentUpdate`, `BulkDocumentResult`,
`EditorDashboard`, `AdminUser`, `Source`, `BackgroundJob`, `AuditEvent`, `SystemService`,
`SystemStatus`, `SystemSettings`, `AdminDashboard`, `JsonValue` и `JsonObject`.

## API contract и FastAPI Этапа 4

Страницы не вызывают `fetch`: только `api` из `src/api`. HTTP adapter всегда использует
`credentials: 'include'`, получает CSRF token перед mutation и повторяет запрос после безопасной
CSRF rotation не более одного раза. Authorization/Bearer header отсутствует.

Editor endpoints:

- `GET /api/editor/dashboard`;
- `GET /api/editor/documents`, `GET /api/editor/documents/:id`;
- `PATCH /api/editor/documents/:id/metadata`;
- `POST /api/editor/documents/:id/hide|restore|reindex`;
- `POST /api/editor/documents/bulk`;
- `GET /api/editor/jobs`.

Admin endpoints:

- `GET /api/admin/dashboard`;
- `GET /api/admin/users`, `GET /api/admin/users/:id`;
- `PATCH /api/admin/users/:id/role`, `POST /api/admin/users/:id/block|unblock`;
- `GET/PATCH /api/admin/sources/:id`, `POST /api/admin/sources/:id/test|sync|stop`;
- `GET /api/admin/jobs`, `GET /api/admin/jobs/:id`;
- `POST /api/admin/jobs/:id/retry|cancel`, `POST /api/admin/jobs/full-reindex`;
- `GET /api/admin/audit`, `GET /api/admin/audit/:id`;
- `GET /api/admin/system`, `POST /api/admin/system/health-check`;
- `GET/PATCH /api/admin/system/settings`.

Пользовательские Stage 1/2 endpoints (`/search`, `/ask`, `/documents`, `/auth`, `/users/me`,
`/history`, `/saved`, `/feedback`) сохранены. Публичный технический status использует
`getPublicSystemStatus`, административный — отдельный `getSystemStatus`.

FastAPI Этапа 4 реализует эти JSON-контракты, единый error envelope, серверную permission matrix,
Argon2id, audit в PostgreSQL, HttpOnly session cookie и credentialed CORS. Для HTTP-режима нужно
установить `VITE_USE_MOCKS=false`, оставить `VITE_API_BASE_URL=http://localhost:8000/api` и
пересобрать frontend. `/api/search` и `/api/ask` до Этапа 6 возвращают честный 501, поэтому
демонстрационный поиск по умолчанию остаётся в mock-режиме.

Браузер никогда не вызывает Ollama напрямую.

## Ingestion UI Этапа 5

При `VITE_USE_MOCKS=false` страницы sources/jobs/system/editor documents используют FastAPI для
sync state, ingestion statistics/failures, job events, chunks и revisions. Start dialog передаёт
mode и безопасные limits, stop запрашивает cooperative cancellation, а auto-refresh TanStack
Query работает только для `QUEUED`/`RUNNING`. Qdrant, Ollama и поисковые индексы не показываются
ONLINE. Mock adapter сохраняет тот же interface для демонстрации без backend.

## Environment

| Переменная              | Default                     | Назначение                      |
| ----------------------- | --------------------------- | ------------------------------- |
| `VITE_USE_MOCKS`        | `true`                      | выбор mock или HTTP adapter     |
| `VITE_API_BASE_URL`     | `http://localhost:8000/api` | FastAPI base URL                |
| `VITE_MOCK_FORCE_ERROR` | `false`                     | принудительный mock error state |

`.env.example` не содержит секретов.

## Production build и Docker

```bash
npm run build
npm run preview
docker build -t pyanswer-frontend .
docker run --rm -p 8080:80 pyanswer-frontend
```

Multi-stage image собирает Vite bundle и отдаёт его через nginx. Конфигурация сохраняет React
Router fallback, immutable assets cache и `/healthz`. Корневой `compose.yaml` Этапа 4 добавляет
PostgreSQL и backend; frontend image остаётся самостоятельным и не включён в compose этого этапа.

# Stage 6.1

В ADMIN-контуре доступна `/admin/indexes`: фактический Qdrant/model/indexer status, версии, full rebuild, validation и безопасный cleanup. Пользовательский HTTP search подключается в 6.2; mock mode сохранён.
