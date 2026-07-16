# Local RAG architecture

`POST /api/ask` и `POST /api/ask/stream` используют один pipeline: normalizer → настоящий
hybrid search → обязательный reranker → PostgreSQL visibility check → deterministic context →
Ollama `qwen3:8b` → citation validation → persistence. FastAPI — единственный клиент Ollama;
браузер никогда не получает внутренний URL модели.

Контекст собирается только из актуальных `CHUNKED`, `UNIQUE`, видимых документов текущей
версии. Максимум chunks на документ и общий token budget ограничены. При недостаточном числе
источников, объёме контекста или reranker score LLM не вызывается: возвращается детерминированный
`insufficientContext=true`.

`rag_responses` хранит финальный ответ, версии prompt/model/index и timings, но не hidden
reasoning. `rag_response_sources` фиксирует citation mapping и retrieval scores. History и
feedback ссылаются на реальный response ID. `clientRequestId` уникален и обеспечивает exactly-once
пersistence при повторе клиента.

Inference gate ограничивает одновременно выполняемые запросы и длину очереди. Disconnect,
AbortController и timeout отменяют Ollama stream; незавершённая запись получает `CANCELLED` или
`FAILED`, а semaphore освобождается.
