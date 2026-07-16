# Indexer worker

`python -m app.indexer` использует очередь jobs Этапа 5 и поддерживает `DOCUMENT_REINDEX`, `FULL_REINDEX`, `SEARCH_INDEX_VALIDATE`, `SEARCH_INDEX_CLEANUP`.

Claim выполняется PostgreSQL `FOR UPDATE SKIP LOCKED`. Lease, heartbeat, stale recovery, cancellation, retry и SIGTERM используют общий durable job engine. Concurrency процесса по умолчанию равна одному. DB transaction никогда не удерживается во время Ollama/Qdrant request.

`DOCUMENT_REINDEX` удаляет stale points документа и ставит READY только после успешного upsert и DB validation. Hide создаёт job удаления points; restore и изменённые chunks создают идемпотентный reindex job.

`FULL_REINDEX` строит новую collection батчами и keyset pagination, проверяет её, атомарно переключает alias и только потом отмечает новую версию ACTIVE.
