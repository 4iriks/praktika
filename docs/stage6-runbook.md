# Stage 6 runbook

1. Поднять PostgreSQL/Qdrant/Ollama: `make qdrant-up && make ollama-up`.
2. Применить migration/bootstrap/seed.
3. Явно скачать модели: `make models-pull && make reranker-model-pull`.
4. Поднять reranker/indexer/backend: `make reranker-up && make indexer-up`.
5. Запустить `make index-full`, дождаться ACTIVE alias и проверить `/api/admin/indexes`.
6. Запустить frontend с `VITE_USE_MOCKS=false`, проверить BM25/vector/hybrid.
7. Проверить JSON `/api/ask`, затем streaming/cancel/citations/feedback/history.
8. Проверить `/admin/rag` и `/admin/system`; unavailable metric показывается `unknown`.

Model missing устраняется только явным pull. При OOM уменьшить `LLM_NUM_CTX`, оставить reranker
на CPU и `OLLAMA_NUM_PARALLEL=1`. Derived Qdrant index можно пересоздать FULL_REINDEX: PostgreSQL
остаётся source of truth. Перед удалением Qdrant volume сохранить snapshot; ACTIVE alias не
удаляется cleanup. Failed rebuild не переключает alias.

Opt-in real smoke запускается только при `RUN_LIVE_LOCAL_MODELS=1`; ordinary tests используют
mock Ollama и реальный disposable Qdrant/PostgreSQL где требуется. Полный corpus rebuild и model
download автоматически не запускаются.
