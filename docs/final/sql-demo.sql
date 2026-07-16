-- PyAnswer final defense queries. Read-only; PostgreSQL 16; latest Alembic schema.

-- 1. Users and roles.
SELECT u.name, u.email, r.code AS role, u.status
FROM users u JOIN roles r ON r.id = u.role_id ORDER BY r.code, u.name;

-- 2. Documents and sources.
SELECT d.external_id, d.normalized_title, s.name, d.source_url
FROM documents d JOIN sources s ON s.id = d.source_id ORDER BY d.created_at DESC LIMIT 20;

-- 3. Documents, selected answers and tags.
SELECT d.external_id, d.normalized_title, a.external_id AS answer_id,
       string_agg(DISTINCT t.display_name, ', ' ORDER BY t.display_name) AS tags
FROM documents d
LEFT JOIN answers a ON a.document_id = d.id AND a.selected_for_corpus
LEFT JOIN document_tags dt ON dt.document_id = d.id
LEFT JOIN tags t ON t.id = dt.tag_id
GROUP BY d.id, a.id ORDER BY d.external_id LIMIT 30;

-- 4. Documents by moderation/processing status.
SELECT status, processing_status, count(*) AS documents
FROM documents GROUP BY status, processing_status ORDER BY documents DESC;

-- 5. Users by role.
SELECT r.code, count(u.id) AS users FROM roles r LEFT JOIN users u ON u.role_id = r.id
GROUP BY r.code ORDER BY r.code;

-- 6. Jobs by type/status.
SELECT type, status, count(*) AS jobs FROM jobs GROUP BY type, status ORDER BY type, status;

-- 7. Popular tags.
SELECT t.display_name, count(DISTINCT dt.document_id) AS documents
FROM tags t JOIN document_tags dt ON dt.tag_id = t.id
GROUP BY t.id ORDER BY documents DESC, t.display_name LIMIT 20;

-- 8. Documents with most current chunks.
SELECT d.external_id, d.normalized_title, count(c.id) AS chunks
FROM documents d JOIN document_chunks c ON c.document_id = d.id
  AND c.document_version = d.version
GROUP BY d.id ORDER BY chunks DESC LIMIT 20;

-- 9. Documents without a ready index.
SELECT external_id, normalized_title, bm25_status, vector_status
FROM documents WHERE bm25_status <> 'READY' OR vector_status <> 'READY'
ORDER BY updated_at DESC LIMIT 30;

-- 10. Last audit events per actor.
SELECT actor_name, actor_role, action, entity_type, outcome, created_at
FROM audit_events ORDER BY created_at DESC LIMIT 30;

-- 11. Job success rate.
SELECT type, count(*) FILTER (WHERE status = 'COMPLETED') AS completed,
       count(*) FILTER (WHERE status = 'FAILED') AS failed,
       round(100.0 * count(*) FILTER (WHERE status = 'COMPLETED') /
             NULLIF(count(*) FILTER (WHERE status IN ('COMPLETED','FAILED')), 0), 2) AS success_pct
FROM jobs GROUP BY type ORDER BY type;

-- 12. Ingestion counters.
SELECT s.name, ss.total_questions_fetched, ss.total_answers_fetched,
       ss.total_documents_inserted, ss.total_documents_updated,
       ss.total_exact_duplicates, ss.total_errors, ss.total_chunks_created
FROM sources s LEFT JOIN source_sync_states ss ON ss.source_id = s.id;

-- 13. Exact content duplicates.
SELECT d.external_id, original.external_id AS duplicate_of, d.content_hash
FROM documents d JOIN documents original ON original.id = d.duplicate_of_document_id
WHERE d.deduplication_status = 'EXACT_DUPLICATE' ORDER BY d.created_at DESC;

-- 14. Changed after last indexing.
SELECT external_id, normalized_title, updated_at, last_indexed_at
FROM documents WHERE last_indexed_at IS NULL OR updated_at > last_indexed_at
ORDER BY updated_at DESC LIMIT 30;

-- 15. Subquery: documents without a successful current index entry.
SELECT d.external_id, d.normalized_title
FROM documents d
WHERE NOT EXISTS (
  SELECT 1 FROM search_index_entries e
  JOIN search_index_versions v ON v.id = e.index_version_id AND v.status = 'ACTIVE'
  WHERE e.document_id = d.id AND e.document_version = d.version AND e.status = 'INDEXED'
) ORDER BY d.updated_at DESC LIMIT 30;

-- 16. CTE: latest job for each source.
WITH ranked_jobs AS (
  SELECT j.*, row_number() OVER (PARTITION BY source_id ORDER BY created_at DESC, id DESC) AS rn
  FROM jobs j WHERE source_id IS NOT NULL
)
SELECT s.name, r.type, r.status, r.progress, r.created_at
FROM sources s LEFT JOIN ranked_jobs r ON r.source_id = s.id AND r.rn = 1;

-- 17. Window function: tag rank within document-count bands.
WITH tag_counts AS (
  SELECT t.id, t.display_name, count(DISTINCT dt.document_id) AS documents
  FROM tags t JOIN document_tags dt ON dt.tag_id = t.id GROUP BY t.id
)
SELECT display_name, documents, dense_rank() OVER (ORDER BY documents DESC) AS popularity_rank
FROM tag_counts ORDER BY popularity_rank, display_name LIMIT 30;

-- 18. Average answers per real document.
SELECT round(avg(answer_count), 2) AS avg_answers
FROM (SELECT d.id, count(a.id) AS answer_count FROM documents d
      LEFT JOIN answers a ON a.document_id = d.id
      WHERE d.external_id NOT LIKE 'stage4-%' GROUP BY d.id) q;

-- 19. Average chunks per processed document.
SELECT round(avg(chunk_count), 2) AS avg_chunks
FROM (SELECT d.id, count(c.id) AS chunk_count FROM documents d
      LEFT JOIN document_chunks c ON c.document_id = d.id AND c.document_version = d.version
      WHERE d.processing_status = 'CHUNKED' GROUP BY d.id) q;

-- 20. Search/RAG history by day.
SELECT date_trunc('day', created_at) AS day, mode,
       count(*) AS requests, round(avg(took_ms), 1) AS avg_ms
FROM search_history GROUP BY day, mode ORDER BY day DESC, mode;
