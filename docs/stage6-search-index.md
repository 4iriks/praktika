# Этап 6.1 — поисковый индекс

PostgreSQL остаётся источником истины, Qdrant — полностью производным индексом. Один актуальный `document_chunk` становится одним point. FastAPI только создаёт durable jobs; отдельный `indexer` выполняет embeddings и Qdrant I/O.

Стек закреплён: Qdrant Server `1.18.2`, `qdrant-client==1.18.0`, Ollama `0.32.0`, `qwen3-embedding:0.6b` (1024 dimensions), native `qdrant/bm25` с IDF. Публичные `/api/search` и `/api/ask` остаются честными 501 до следующих частей Этапа 6.

## Запуск

```bash
docker-compose up -d postgres qdrant ollama
docker-compose run --rm backend alembic upgrade head
make embedding-model-pull
make indexer-up
```

Полный rebuild запускается ADMIN на `/admin/indexes`; alias `pyanswer_chunks_current` переключается только после сверки count, schema и sample query. Старый ACTIVE индекс становится RETIRED и сохраняется для rollback.

## Ограничения 6.1

- модель не скачивается при build, migration, tests или старте backend;
- полный корпус автоматически не переиндексируется;
- reranker, Search API и RAG относятся к 6.2/6.3;
- base Compose работает без GPU, `compose.gpu.yaml` включает NVIDIA для Ollama.
