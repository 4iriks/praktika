# PyAnswer

PyAnswer — локальная поисковая и RAG-система по вопросам о Python со Stack Overflow на
русском. PostgreSQL хранит исходный корпус, Qdrant — производный dense/sparse индекс, а
Ollama запускает локальные embedding- и generation-модели. Browser работает только с единым
origin Nginx; прямого доступа к PostgreSQL, Qdrant и Ollama нет.

## Возможности

- React + TypeScript frontend и FastAPI backend;
- регистрация, HttpOnly sessions, CSRF, Argon2id и серверный RBAC USER/EDITOR/ADMIN;
- durable ingestion/index jobs с lease, heartbeat, checkpoint, cancellation и retry;
- Stack Exchange pagination, quota/backoff, очистка HTML и сохранение Python-кода;
- identity/exact-content deduplication, revisions и детерминированные chunks;
- Qdrant sparse BM25, dense HNSW, weighted RRF и локальный reranker;
- grounded RAG через Ollama с insufficient-context gate, SSE и проверяемыми citations;
- audit, operational panels, manifests, consistency checks и backup validation.

## Системные требования

- Ubuntu/Linux, Docker Engine и Docker Compose plugin либо `docker-compose`;
- 32 ГБ RAM рекомендовано; CPU-режим поддерживается;
- NVIDIA GPU необязателен. Для `compose.gpu.yaml` нужны рабочий драйвер и NVIDIA Container
  Toolkit;
- минимум 35 ГБ свободного дискового бюджета проекта. Команда `make disk-report` показывает
  фактические доступные измерения и честно отмечает недоступные.

Версии сервисов и моделей закреплены в [compose.yaml](compose.yaml) и
[config/models.yaml](config/models.yaml). Большие модели не скачиваются при build, migration,
tests или обычном `demo-up`.

## Первый запуск

```bash
make first-run
```

Команда создаёт локальный `.env`, только если файла ещё нет, запускает инфраструктуру,
применяет migrations, выполняет идемпотентные bootstrap/demo seed и выводит статус. Она не
скачивает большие модели и не запускает полный импорт.

Затем явно загрузите модели и поднимите demo:

```bash
make models-check
make models-pull
make demo-up
```

Единый адрес: **http://localhost:8080**. Swagger в development доступен через
`http://localhost:8080/api/docs`.

Demo accounts предназначены только для локальной демонстрации:

| Роль | Email | Пароль |
|---|---|---|
| USER | `user@pyanswer.local` | `Demo123!` |
| EDITOR | `editor@pyanswer.local` | `Demo123!` |
| ADMIN | `admin@pyanswer.local` | `Demo123!` |

## Корпус и индекс

Сначала получите `SOURCE_ID` на странице `/admin/sources` или из локального ingestion report.

```bash
make import-smoke SOURCE_ID=<uuid>
RUN_LIVE_MINIMUM_IMPORT=1 make import-minimum SOURCE_ID=<uuid>
CONFIRM_INDEX_FULL=YES make index-full
make index-status
```

Импорт без лимита защищён явным флагом:

```bash
RUN_FULL_IMPORT=1 make import-full SOURCE_ID=<uuid>
```

Ни `first-run`, ни tests не запускают живой импорт. Источник, attribution и URL сохраняются;
синтетические записи не учитываются как выполнение минимального корпуса.

## Проверки и отчёты

```bash
make verify-all
make corpus-manifest
make data-check
make index-check
make disk-report
make demo-check
```

Фактические отчёты создаются в `artifacts/` и используют статусы `PASS`, `WARNING`, `FAIL` и
`NOT_RUN`. Невыполненная live-проверка никогда не превращается в PASS.

Evaluation запускается только на вручную проверенных (`reviewed=true`) qrels:

```bash
make evaluate
```

Dataset находится в `evaluation/`; порядок ручной разметки описан в
[evaluation-review.md](docs/final/evaluation-review.md).

## Backup и restore drill

```bash
make backup
make restore-check BACKUP_PATH=backups/<timestamp>
```

Backup включает `pg_dump`, Qdrant snapshot при наличии active alias, manifests и checksums,
но не `.env`, cookies, API keys или Ollama binaries. Restore check использует disposable
окружение и не перезаписывает основную БД.

## Разработка

Backend:

```bash
cd backend
python -m pip install -e '.[dev]'
ruff check .
ruff format --check .
mypy app
pytest --cov=app --cov-report=term-missing --cov-fail-under=80
```

Frontend:

```bash
cd frontend
npm install
npm run typecheck
npm run lint
npm run test
npm run build
npm run format:check
```

Mock frontend mode сохранён для изолированной разработки. Production frontend image собирается
с `VITE_USE_MOCKS=false` и `/api` на том же origin.

## Документация

- [Архитектура ingestion](docs/stage5-ingestion.md),
  [worker](docs/worker-architecture.md) и [полный import runbook](docs/ingestion-runbook.md);
- [Qdrant/indexer](docs/stage6-search-index.md), [hybrid ranking](docs/hybrid-ranking.md),
  [RAG](docs/rag-architecture.md) и [Stage 6 runbook](docs/stage6-runbook.md);
- [ERD](docs/erd.md), [API contract](docs/api-contract.md) и
  [SQL для защиты](docs/final/sql-demo.md);
- [traceability](docs/final/requirements-traceability.md),
  [отчёт](docs/final/report-source.md), [презентация](docs/final/presentation-outline.md),
  [demo script](docs/final/demo-script.md) и [вопросы защиты](docs/final/defense-qa.md);
- [troubleshooting](docs/final/troubleshooting.md).

## Ограничения и attribution

Qdrant является восстанавливаемым индексом, а PostgreSQL — source of truth. На CPU первичная
индексация и локальная генерация заметно медленнее GPU. Evaluation без проверенной ручной
разметки считается preliminary. Контент принадлежит авторам Stack Overflow на русском и
используется с сохранением ссылок, авторства и доступной лицензии источника.
