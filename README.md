# PyAnswer

PyAnswer — локальная интеллектуальная поисковая система по русскоязычным вопросам и ответам о
Python со Stack Overflow на русском. Репозиторий содержит завершённый frontend Этапов 1–3,
серверный фундамент Этапа 4 и инфраструктуру ingestion подэтапа 5.1.

## Состояние проекта

- `frontend/` — React, TypeScript strict, Vite, React Router, Tailwind CSS и TanStack Query;
- `backend/` — FastAPI, Pydantic v2, async SQLAlchemy 2.x, PostgreSQL и Alembic;
- cookie-auth — opaque server-side session, HttpOnly-cookie и CSRF double-submit token;
- Argon2id — единственный формат серверного password hash;
- RBAC — USER, EDITOR и ADMIN с повторной проверкой permissions на сервере;
- PostgreSQL — users, sessions, documents, answers, tags, history, saved, feedback, jobs, audit,
  sources и system settings;
- ingestion 5.1 — durable PostgreSQL queue, отдельный worker, checkpoint/events и типизированный
  Stack Exchange API client;
- mock mode frontend сохранён и остаётся значением по умолчанию;
- `/api/search` выполняет настоящий BM25/vector/hybrid retrieval через Qdrant;
- `/api/ask` и `/api/ask/stream` выполняют локальный grounded RAG через Ollama.

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
make worker-up
```

Worker использует тот же backend image, не публикует порт и запускается отдельно от FastAPI.
`make worker-health` показывает container state и последние heartbeat records.

Локальный запуск без Docker описан в [backend/README.md](backend/README.md). Swagger в
development доступен по `http://localhost:8000/api/docs`.

Demo seed создаёт:

| Роль   | Email                   | Пароль     |
| ------ | ----------------------- | ---------- |
| USER   | `user@pyanswer.local`   | `Demo123!` |
| EDITOR | `editor@pyanswer.local` | `Demo123!` |
| ADMIN  | `admin@pyanswer.local`  | `Demo123!` |

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
- [Worker architecture](docs/worker-architecture.md);
- [Stack Exchange client](docs/stackexchange-client.md);
- [Ingestion Этапа 5](docs/stage5-ingestion.md);
- [Runbook полной загрузки](docs/ingestion-runbook.md);
- [Поисковый индекс Этапа 6](docs/stage6-search-index.md);
- [Hybrid ranking](docs/hybrid-ranking.md) и [retrieval evaluation](docs/retrieval-evaluation.md);
- [Архитектура RAG](docs/rag-architecture.md), [SSE](docs/rag-streaming.md),
  [безопасность](docs/rag-security.md) и [runbook Этапа 6](docs/stage6-runbook.md);
- сохранённые задания: [Этап 4](docs/prompts/stage-4.md) и
  [полный комплект Этапа 5](docs/prompts/stage-5.md) с отдельными промтами 5.1–5.3.

## Этап 5: ingestion Stack Exchange

Отдельный worker обрабатывает durable PostgreSQL jobs с claim/lease/heartbeat, checkpoint,
cancellation и stale recovery. Типизированный клиент получает вопросы постранично и ответы
batch-запросами до 100 ID, соблюдает `has_more`, quota, backoff и ограниченные retries. Pipeline
очищает HTML, сохраняет код, выбирает ответы, строит canonical SHA-256 hashes, revisions и
детерминированные chunks. ADMIN/EDITOR UI показывает реальный прогресс и состояние корпуса.

Полный импорт 25 000 веток автоматически не запускается; см. [runbook](docs/ingestion-runbook.md).
Поиск не имитируется через SQL. Qdrant содержит dense HNSW и native sparse BM25, hybrid
использует weighted RRF и локальный reranker.

# Этап 6

Проект получил self-hosted Qdrant, dense embeddings через Ollama, native sparse BM25,
durable indexer и blue-green переиндексацию. HTTP mode поддерживает BM25, vector и hybrid
поиск и weighted RRF. Локальный RAG использует обязательный reranker и Ollama `qwen3:8b`,
проверяет insufficient context до вызова LLM, stream-ит только answer content и валидирует
citations. Модели скачиваются только явной командой `make models-pull`.
