# Этап 6.1–6.2 — поисковый индекс и retrieval

PostgreSQL остаётся источником истины, Qdrant — полностью производным индексом. Один актуальный `document_chunk` становится одним point. FastAPI только создаёт durable jobs; отдельный `indexer` выполняет embeddings и Qdrant I/O.

Стек закреплён: Qdrant Server `1.18.2`, `qdrant-client==1.18.0`, Ollama `0.32.0`, `qwen3-embedding:0.6b` (1024 dimensions), native `qdrant/bm25` с IDF и `Qwen/Qwen3-Reranker-0.6B` revision `e1775d95f8cf4625eea7879c6edb34beae6c42af`. `/api/search` выполняет BM25, dense или hybrid retrieval; локальный RAG описан в `rag-architecture.md`.

## Запуск

```bash
docker-compose up -d postgres qdrant ollama
docker-compose run --rm backend alembic upgrade head
make embedding-model-pull
make indexer-up
```

Полный rebuild запускается ADMIN на `/admin/indexes`; alias `pyanswer_chunks_current` переключается только после сверки count, schema и sample query. Старый ACTIVE индекс становится RETIRED и сохраняется для rollback.

## Ограничения 6.2

- модель не скачивается при build, migration, tests или старте backend;
- полный корпус автоматически не переиндексируется;
- RAG и генерация LLM относятся к 6.3;
- base Compose работает без GPU, `compose.gpu.yaml` включает NVIDIA для Ollama.
