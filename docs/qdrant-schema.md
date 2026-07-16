# Qdrant schema

Alias: `pyanswer_chunks_current`. Физические collections имеют вид `pyanswer_chunks_<schema-hash>_<timestamp>_<job>`.

Named vectors:

- `dense`: 1024, cosine, HNSW `m=16`, `ef_construct=100`;
- `sparse`: native `qdrant/bm25`, IDF modifier, Russian lowercase tokenization.

Payload indexes: `document_id`, `source_id`, `tags`, `published_at`, `question_score`, `accepted_answer`, `has_code`, `section_type`, `document_status`, `processing_status`, `deduplication_status`, `document_version`.

В payload нет raw HTML, auth/session/cookie данных, ключей и vectors. Полный текст остаётся в PostgreSQL. Point UUIDv5 детерминирован по chunk ID, версии документа, content hash и версии схемы.

Eligible: только непустой актуальный chunk документа `CHUNKED`, `ACTIVE/OUTDATED`, `UNIQUE`, без processing error. HIDDEN, FAILED, PENDING, EXACT_DUPLICATE и старые версии исключаются.
