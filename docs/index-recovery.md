# Восстановление индекса

- Qdrant outage: job остаётся durable и повторяется только в пределах `INDEX_JOB_MAX_ATTEMPTS`.
- Ошибка/cancel full rebuild: alias остаётся на прежней collection, BUILDING/FAILED collection не становится ACTIVE.
- Ошибка DB после alias operation: indexer компенсирует переключение на прежний target.
- Cleanup по умолчанию dry-run; ACTIVE и alias target никогда не удаляются.
- `INDEX_RETAIN_RETIRED_COUNT=1` сохраняет предыдущую версию для rollback.

Qdrant — производные данные: его можно пересоздать из PostgreSQL без удаления documents/chunks/revisions.
