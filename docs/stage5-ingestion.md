# PyAnswer — Этап 5, подэтапы 5.1–5.2

Подэтап 5.1 добавил durable PostgreSQL queue, отдельный worker и типизированный Stack Exchange
client. Подэтап 5.2 завершает реальный `SOURCE_SYNC`: вопросы, ответы, теги, ревизии и чанки
сохраняются в PostgreSQL. Полный импорт 25 000 веток по-прежнему не запускается автоматически.

## Поток данных

1. ADMIN создаёт `SOURCE_SYNC`; HTTP endpoint только фиксирует job и audit.
2. Worker атомарно захватывает job через `FOR UPDATE SKIP LOCKED` и выполняет сеть вне DB
   transaction.
3. Для страницы до 100 вопросов клиент пакетно получает все страницы ответов.
4. Каждый thread очищается, нормализуется и сохраняется короткой транзакцией.
5. После committed batch worker обновляет counters, `source_sync_states` и job checkpoint.
6. Cancellation, quota pause или restart продолжаются с последнего checkpoint. Для ограничения
   внутри страницы сохраняется `itemOffset`, поэтому документы не пропускаются.

## Initial и incremental

`AUTO` выбирает `INITIAL`, пока `initial_sync_completed_at` пуст, затем `INCREMENTAL`.

- INITIAL: `sort=creation`, `order=desc`, фиксированный `todate`, продолжение по page/offset до
  target, конца API или явно заданного безопасного cap.
- INCREMENTAL: `sort=activity`, `fromdate = watermark - overlap`, фиксированный `todate`.
- Watermark и признак завершения initial обновляются в той же финальной транзакции, где job
  становится `COMPLETED`. FAILED/CANCELLED job их не продвигает.
- Ограниченный успешный запуск сохраняет checkpoint, но не объявляет весь snapshot завершённым.
- Dry-run сохраняет только job checkpoint и никогда не меняет production sync state.

## Обработка thread

Pipeline выполняет parser-based HTML cleaning, сохраняет fenced code blocks, выбирает accepted и
до трёх дополнительных ответов, строит canonical document и два SHA-256 hash. Identity
`source_id + external_id` обеспечивает upsert, одинаковый canonical content помечается как
`EXACT_DUPLICATE` без физического удаления.

Смысловое изменение увеличивает `documents.version`, создаёт `document_revisions` и атомарно
заменяет `document_chunks`. Metadata-only изменение не пересоздаёт revision/chunks. Отсутствующий
ранее известный answer помечается `source_missing`, но не удаляется.

## Processing и индексы

Технические состояния: `RAW`, `CLEANING`, `CLEANED`, `CHUNKING`, `CHUNKED`, `FAILED`.
Дедупликация: `UNIQUE`, `EXACT_DUPLICATE`, `POSSIBLE_DUPLICATE`.

Успешный ingestion выставляет BM25/vector только в `NOT_INDEXED` или `OUTDATED`. Значение
`READY` не используется без реального индекса Этапа 6. `/api/search` и `/api/ask` в HTTP mode
продолжают честно возвращать 501.

## Failure isolation

Ошибка качества отдельного thread сохраняется в `ingestion_failures` с безопасным кодом и не
останавливает страницу. Ошибка клиента, схемы API или PostgreSQL завершает/requeues всю job по
типизированным правилам. Raw HTML, API key и полный API wrapper в failures/events не сохраняются.

Operational API:

- `GET /api/admin/sources/{sourceId}/sync-state`;
- `GET /api/admin/ingestion/stats`;
- `GET /api/admin/ingestion/failures`;
- `GET /api/admin/ingestion/failures/{failureId}`;
- ADMIN/EDITOR job events согласно существующим permissions.

## Проверки и запуск

Обычные tests используют реальный disposable PostgreSQL и mocked HTTP. Они проверяют очистку,
selection, hashes, дедупликацию, revisions, deterministic chunks, initial/incremental,
page-offset resume, cancellation и failure isolation.

```bash
make backend-migrate
make worker-up
make worker-health
make worker-logs
```

Live/full import не является автоматической проверкой 5.2. UI-интеграция, capped live smoke и
полный runbook завершаются в подэтапе 5.3.
