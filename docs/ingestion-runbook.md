# Runbook загрузки корпуса Stack Exchange

Полный импорт не запускается миграцией, seed, тестами или Docker build. До начала сохраните
backup PostgreSQL и убедитесь, что на диске доступно не менее 35 ГБ проектного лимита.

1. Запустить PostgreSQL, применить migrations и выполнить bootstrap.
2. Запустить backend и `make worker-up`; проверить `make worker-health`.
3. В ADMIN UI выполнить test connection и проверить quota.
4. Узнать UUID source в `/admin/sources` или PostgreSQL.
5. Выполнить capped smoke: `make sync-smoke SOURCE_ID=<uuid>`.
6. Проверить documents, answers, chunks, job events и `make ingestion-report`.
7. Для полного INITIAL явно выполнить
   `make sync-full-confirmed SOURCE_ID=<uuid> CONFIRM_FULL_SYNC=YES`.
8. Следить за quota, heartbeat, checkpoint и failures в UI; не перезапускать активную job.
9. Stop выставляет cancellation request; worker сохранит последний committed checkpoint.
10. Повторный AUTO продолжит INITIAL. После полного snapshot AUTO выберет INCREMENTAL;
    capped-команда: `make sync-incremental SOURCE_ID=<uuid>`.
11. Проверить минимум 5 000 документов; целевой корпус — около 25 000 веток.

Opt-in сетевой smoke клиента, не сохраняющий документы:

```bash
RUN_LIVE_STACKEXCHANGE_SMOKE=1 python -m app.scripts.live_stackexchange_smoke
```

API key задаётся только environment и не выводится CLI. Qdrant/BM25/vector indexing на Этапе 5
не запускаются; новые документы остаются `NOT_INDEXED`/`OUTDATED`.
