# PyAnswer

PyAnswer — локальная интеллектуальная поисковая система по русскоязычным вопросам и ответам о
Python со Stack Overflow на русском. Репозиторий содержит завершённый frontend Этапов 1–3 и
серверный фундамент Этапа 4.

## Состояние проекта

- `frontend/` — React, TypeScript strict, Vite, React Router, Tailwind CSS и TanStack Query;
- `backend/` — FastAPI, Pydantic v2, async SQLAlchemy 2.x, PostgreSQL и Alembic;
- cookie-auth — opaque server-side session, HttpOnly-cookie и CSRF double-submit token;
- Argon2id — единственный формат серверного password hash;
- RBAC — USER, EDITOR и ADMIN с повторной проверкой permissions на сервере;
- PostgreSQL — users, sessions, documents, answers, tags, history, saved, feedback, jobs, audit,
  sources и system settings;
- mock mode frontend сохранён и остаётся значением по умолчанию;
- HTTP endpoints `/api/search` и `/api/ask` честно возвращают 501 до Этапа 6.

## Быстрый запуск frontend

```bash
cd frontend
npm install
npm run dev
```

По умолчанию `VITE_USE_MOCKS=true`, поэтому весь пользовательский, редакторский и
административный сценарий работает без backend.

## PostgreSQL и backend

Создайте локальный `.env` по корневому `.env.example`, задав собственный
`POSTGRES_PASSWORD`. Файл `.env` не попадает в Git.

```bash
docker compose up -d postgres
docker compose run --rm backend alembic upgrade head
docker compose run --rm backend python -m app.scripts.bootstrap
docker compose run --rm backend python -m app.scripts.seed_demo
docker compose up backend
```

Локальный запуск без Docker описан в [backend/README.md](backend/README.md). Swagger в
development доступен по `http://localhost:8000/api/docs`.

Demo seed создаёт:

| Роль | Email | Пароль |
| --- | --- | --- |
| USER | `user@pyanswer.local` | `Demo123!` |
| EDITOR | `editor@pyanswer.local` | `Demo123!` |
| ADMIN | `admin@pyanswer.local` | `Demo123!` |

Эти данные предназначены только для локальной демонстрации. В production demo seed выключен.

## Проверки

Backend, при настроенном disposable `TEST_DATABASE_URL` с `test` в имени БД:

```bash
cd backend
ruff check .
ruff format --check .
mypy app
pytest --cov=app --cov-report=term-missing --cov-fail-under=80
alembic upgrade head
alembic check
```

Frontend:

```bash
cd frontend
npm run typecheck
npm run lint
npm run test
npm run build
npm run format:check
```

## Документация

- [Этап 4](docs/backend-stage4.md);
- [ER-диаграмма](docs/erd.md);
- [API contract](docs/api-contract.md);
- [SQL-примеры](docs/sql_examples.sql);
- сохранённые задания: [Этап 4](docs/prompts/stage-4.md) и
  [полученная часть Этапа 5](docs/prompts/stage-5.md).

## Границы Этапа 4

Backend не имитирует BM25, HNSW, embeddings, Qdrant, Ollama или RAG через SQL. Фоновые jobs на
этом этапе надёжно сохраняются как `QUEUED`, но worker появится на Этапе 5. Настоящие search и
RAG будут подключены позднее. Frontend permission checks отвечают за UX; защитой являются только
серверные session, permission dependencies, service rules и PostgreSQL constraints.
