# PyAnswer frontend

PyAnswer — локальная интеллектуальная поисковая система по синтетической русскоязычной базе
вопросов и ответов о Python. Frontend реализует законченный пользовательский контур:

`регистрация → вход → поиск или RAG → история → сохранённые документы → профиль → feedback`.

Этап 2 работает без backend, PostgreSQL, Qdrant и настоящего Ollama. Поиск, RAG и
пользовательские операции обслуживает типизированный mock-адаптер. Существующий сценарий Этапа 1
«главная → поиск или RAG → документ» сохранён.

## Стек

- React 18 и TypeScript в strict-режиме;
- Vite, React Router и TanStack Query;
- Tailwind CSS, Lucide React и Sonner;
- React Markdown, remark-gfm и react-syntax-highlighter;
- Vitest, Testing Library, ESLint и Prettier;
- production multi-stage Docker image с nginx.

Требуются Node.js 18+ и npm 9+.

## Локальный запуск

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Vite запускает приложение по адресу `http://localhost:5173`.

Полная проверка:

```bash
npm run typecheck
npm run lint
npm run test
npm run build
npm run format:check
```

## Маршруты

Публичные маршруты:

- `/` — Spotlight-поиск, состояние индекса и вход в пользовательский контур;
- `/search` — документная выдача и mock RAG с URL-состоянием;
- `/documents/:documentId` — полная ветка вопроса и ответов;
- `/login` — вход с безопасным `returnTo`;
- `/register` — регистрация и автоматический вход;
- `/403` — недостаточно прав;
- `*` — страница 404.

Маршруты под `ProtectedRoute`:

- `/profile` — профиль, статистика и поисковые настройки;
- `/history` — личная история поисков и RAG-запросов;
- `/saved` — личная библиотека документов.

Неавторизованный пользователь перенаправляется на `/login`. Параметр `returnTo` принимает только
внутренний путь, начинающийся с одного `/`; внешние URL и пути вида `//example.org` отклоняются.

Поддерживаемые параметры `/search`: `q`, `view`, `mode`, `page`, `page_size`, `tags`, `min_score`,
`accepted`, `has_code`, `sort`. Явные параметры URL имеют приоритет над настройками профиля.

## Mock-режим

По умолчанию используется `VITE_USE_MOCKS=true`. Mock API имитирует задержки, ошибки,
фильтрацию, сортировку, pagination, streaming RAG и server-like пользовательские операции. В базе
22 синтетических документа; большие фрагменты реальных публикаций не копируются.

Демонстрационный аккаунт:

```text
user@pyanswer.local
Demo123!
```

Дополнительные аккаунты создаются на `/register`. Email сравнивается без учёта регистра, пароль
проверяется по требованиям формы, всем новым пользователям назначается роль `USER`.

Для принудительной проверки error state:

```env
VITE_MOCK_FORCE_ERROR=true
```

Запрос `__error__` также вызывает тестовую ошибку поиска. Запрос вне локальной тематики, например
«квантовая хромодинамика», демонстрирует RAG-сценарий недостаточного контекста.

### Mock credentials и сессия

Пользовательское mock-хранилище изолировано в `src/mocks` и использует versioned namespace
`pyanswer:mock:v1:*`. UI-компоненты не управляют auth-сессией напрямую.

- mock credentials содержат случайную salt и digest Web Crypto, но не открытый пароль;
- публичный `User` не содержит password, digest или salt;
- сессия содержит только `userId`, `expiresAt` и `mockSessionVersion`;
- при «Запомнить меня» ссылка сессии хранится в `localStorage`;
- без запоминания ссылка сессии хранится в `sessionStorage`;
- повреждённые JSON-записи безопасно отбрасываются;
- данные истории, сохранений, preferences и feedback разделены по `userId`.

Browser-side digest — только демонстрационный mock-механизм и не является безопасной
production-аутентификацией. В следующем серверном этапе проверка credentials должна выполняться в
FastAPI с Argon2, а сессия — передаваться через защищённую `HttpOnly` cookie. Frontend не хранит
секреты и не добавляет Bearer-заголовок.

Чтобы сбросить mock-данные, откройте DevTools → Application → Storage → Clear site data или удалите
ключи с префиксом `pyanswer:mock:` из Local Storage и Session Storage для локального origin.

### История, сохранения и feedback

- успешный поиск или RAG авторизованного пользователя автоматически создаёт одну запись истории;
- пустые, гостевые и неуспешные запросы не записываются;
- быстрые технические повторы дедуплицируются;
- повтор из истории восстанавливает режим, представление, фильтры, сортировку и размер страницы;
- сохранение документа идемпотентно и синхронизируется через точечную invalidation TanStack Query;
- у пользователя может быть только одна актуальная оценка конкретного RAG-response;
- positive/negative feedback можно изменить или удалить;
- отрицательная оценка поддерживает необязательную причину и комментарий до 500 символов.

## Пользовательские настройки

На `/profile` сохраняются индивидуальные значения:

- режим поиска по умолчанию: BM25, Vector или Hybrid;
- представление по умолчанию: документы или ответ ИИ;
- 10, 20 или 50 результатов на странице;
- автоматическое раскрытие технических score;
- подтверждение перехода на внешний источник.

Настройки применяются к новым поискам с главной страницы и не заменяют явно переданные параметры
URL. Изменение email проверяет формат и уникальность, не завершает текущую сессию и применяется к
следующему входу.

## Архитектура

```text
src/
  api/          единый контракт, mock/HTTP selection, query keys и cache helpers
  app/          providers, QueryClient и Error Boundary
  components/   UI, dialogs, navigation и технические панели
  features/     auth, search, RAG и documents
  hooks/        общие клавиатурные хуки
  layouts/      адаптивный workspace с mobile drawers
  mocks/        данные, repository, versioned storage и mock API
  pages/        маршрутные страницы
  routes/       конфигурация публичных и защищённых маршрутов
  store/        тема интерфейса
  test/         тестовые providers и browser setup
  types/        публичные доменные TypeScript-типы
  utils/        URL, валидация и форматирование
```

Server-like данные пользователя находятся в TanStack Query: current user, статистика, история,
сохранённые документы и feedback. `AuthContext` предоставляет только auth-status, текущего
пользователя и auth-actions. При logout удаляется пользовательская часть query cache, системный
status cache сохраняется.

Основные новые типы Этапа 2: `RegisterRequest`, `LoginRequest`, `AuthSession`, `AuthStatus`,
`AccountStatus`, `UpdateProfileRequest`, `UserPreferences`, `UserStats`, `SearchHistoryItem`,
`HistoryFilters`, `HistoryResponse`, `SavedDocument`, `SavedDocumentsFilters`,
`SavedDocumentsResponse`, `FeedbackValue`, `FeedbackReason`, `Feedback` и `RagResponseId`.

## API adapter и будущий FastAPI

Страницы и feature-компоненты не вызывают `fetch` напрямую. Они используют `api` из
`src/api/index.ts`, который выбирает одинаково типизированные `mockApi` или `httpApi`. HTTP-адаптер
всегда отправляет `credentials: 'include'` для будущей cookie-сессии.

Поиск и документы:

- `searchDocuments` → `GET /api/search`;
- `askQuestion` → `POST /api/ask`;
- `getDocument` → `GET /api/documents/:documentId`;
- `getSystemStatus` → `GET /api/status`.

Аутентификация и профиль:

- `register` → `POST /api/auth/register`;
- `login` → `POST /api/auth/login`;
- `logout` → `POST /api/auth/logout`;
- `getCurrentUser` → `GET /api/auth/me`;
- `updateCurrentUser` → `PATCH /api/users/me`;
- `getUserStats` → `GET /api/users/me/stats`.

История, сохранения и feedback:

- `getHistory` → `GET /api/history`;
- `deleteHistoryItem` → `DELETE /api/history/:historyId`;
- `clearHistory` → `DELETE /api/history`;
- `getSavedDocuments` → `GET /api/saved`;
- `saveDocument` → `POST /api/saved/:documentId`;
- `unsaveDocument` → `DELETE /api/saved/:documentId`;
- `sendFeedback` → `POST /api/feedback`;
- `deleteFeedback` → `DELETE /api/feedback/:feedbackId`;
- `getFeedbackForResponse` → `GET /api/feedback/by-response/:responseId`.

Для подключения FastAPI:

1. реализовать endpoint с JSON-контрактами из `src/types`;
2. хранить credentials и Argon2 digest только на сервере;
3. выдавать сессионную `HttpOnly`, `Secure`, `SameSite` cookie;
4. настроить CORS с credentials для точного frontend origin;
5. установить `VITE_USE_MOCKS=false`;
6. задать `VITE_API_BASE_URL=http://localhost:8000/api`;
7. перезапустить Vite или пересобрать production bundle.

Прямая интеграция браузера с Ollama не предусмотрена: будущий локальный LLM вызывается только
backend-сервисом.

## Переменные окружения

| Переменная            | Значение по умолчанию     | Назначение                   |
| --------------------- | ------------------------- | ---------------------------- |
| VITE_USE_MOCKS        | true                      | Выбор mock или HTTP adapter  |
| VITE_API_BASE_URL     | http://localhost:8000/api | Базовый URL будущего FastAPI |
| VITE_MOCK_FORCE_ERROR | false                     | Принудительный mock error    |

`.env.example` не содержит секретов.

## Production build и Docker

Локальная production-сборка:

```bash
npm run build
npm run preview
```

Bundle создаётся в `dist/`.

Docker frontend:

```bash
docker build -t pyanswer-frontend .
docker run --rm -p 8080:80 pyanswer-frontend
```

Multi-stage image собирает Vite bundle и обслуживает его через nginx. Конфигурация включает React
Router fallback, immutable cache для assets и healthcheck `/healthz`. Полный `docker-compose` на
этом этапе не используется.
