# Search troubleshooting

- `503 Активный поисковый индекс отсутствует`: завершить FULL_REINDEX и проверить alias.
- `EMBEDDING_MODEL_MISSING`: выполнить `make embedding-model-pull`.
- reranker fallback: выполнить `make reranker-model-pull && make reranker-up` либо включить обязательный режим только после health check.
- пустая выдача: проверить eligibility chunks и `staleDiscarded`.
- Qdrant offline: проверить `docker compose ps qdrant` и `/admin/indexes`.
- deep pagination 422: уменьшить `page * pageSize`; retrieval ограничен candidate window.
