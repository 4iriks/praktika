# Финальный acceptance checklist

Источник результата — `artifacts/acceptance-report.{json,md}`. Отметка ниже не заменяет
машиночитаемый отчёт.

- [x] PostgreSQL ready, Alembic at head.
- [x] Backend и frontend доступны через `http://localhost:8080`.
- [x] Ingestion/index workers имеют свежий heartbeat.
- [x] Не менее 5 000 реальных CHUNKED документов (фактически 10 700).
- [x] Data consistency = PASS.
- [x] Qdrant alias и активная index version согласованы.
- [x] Point count согласован с eligible chunks (25 214).
- [x] Embedding, reranker и generation models доступны.
- [x] BM25, Vector, Hybrid и reranker smoke выполнены.
- [x] RAG streaming и citations smoke выполнены.
- [x] USER, EDITOR, ADMIN login и серверный RBAC проверены.
- [ ] Playwright E2E не реализован; критический путь проверен live HTTP acceptance.
- [x] Backup создан, restore validation выполнен без изменения основных volumes.
- [x] Disk budget не превышен.
- [x] Security review и npm production audit выполнены; `pip-audit` NOT_RUN.
- [x] Невыполненные live-пункты отмечены NOT_RUN, а не PASS.
