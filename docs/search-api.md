# Search API

`GET /api/search` использует только alias `pyanswer_chunks_current`. Режимы: `bm25`, `vector`, `hybrid`. Параметры совместимы с frontend: `q`, `mode`, `page`, `page_size`, `tags`, `min_score`, `accepted`, `has_code`, `sort`; дополнительно доступны даты, source и section type.

Response сохраняет прежние `results`, `pagination`, `metrics` и добавляет component ranks/scores, `fusionScore`, nullable `rerankerScore`, matched chunks, index version и подробные timings. `total` — число документов внутри ограниченного candidate window, поэтому `totalIsExact=false`.

Qdrant payload всегда фильтруется по ACTIVE/OUTDATED, CHUNKED и UNIQUE. После retrieval PostgreSQL повторно проверяет текущую version и visibility: stale или скрытый point отбрасывается.
