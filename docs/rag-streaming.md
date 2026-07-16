# RAG streaming contract

`POST /api/ask/stream` — credentialed, CSRF-protected `text/event-stream`. Используется `fetch`,
поскольку запрос POST содержит JSON и cookie. Events содержат JSON:

- `started` — request ID;
- `status` — validating/searching/fusing/reranking/selecting_sources/generating/
  validating_citations/saving/completed;
- `sources` — проверенные source cards до tokens;
- `token` — только visible answer content;
- `heartbeat` — редкий keepalive;
- `metrics` — timings/confidence;
- `done` — полный совместимый `AskResponse`;
- `error` — безопасные code/message.

Thinking events отсутствуют. Parser устойчив к UTF-8 chunks и malformed lines. AbortController
закрывает stream; backend проверяет disconnect и отменяет provider request. Повтор с тем же
`clientRequestId` не создаёт второй response/history.
