-- 1. Пользователи и их роли.
SELECT u.id, u.name, u.email, r.code AS role, u.status
FROM users AS u
JOIN roles AS r ON r.id = u.role_id
ORDER BY u.registered_at DESC, u.id;

-- 2. Документы по источникам.
SELECT s.id, s.name, COUNT(d.id) AS documents_count, COALESCE(SUM(d.chunks_count), 0) AS chunks
FROM sources AS s
LEFT JOIN documents AS d ON d.source_id = s.id
GROUP BY s.id, s.name
ORDER BY documents_count DESC, s.id;

-- 3. Пользователи по ролям и статусам.
SELECT r.code AS role, u.status, COUNT(*) AS users_count
FROM users AS u
JOIN roles AS r ON r.id = u.role_id
GROUP BY r.code, u.status
ORDER BY r.code, u.status;

-- 4. Документы без завершённой подготовки обоих индексов.
SELECT d.id, d.normalized_title, d.bm25_status, d.vector_status
FROM documents AS d
WHERE d.id IN (
  SELECT candidate.id
  FROM documents AS candidate
  WHERE candidate.bm25_status <> 'READY' OR candidate.vector_status <> 'READY'
)
ORDER BY d.updated_at DESC, d.id;

-- 5. Популярные теги.
SELECT t.normalized_name, COUNT(DISTINCT dt.document_id) AS documents_count
FROM tags AS t
JOIN document_tags AS dt ON dt.tag_id = t.id
GROUP BY t.id, t.normalized_name
ORDER BY documents_count DESC, t.normalized_name
LIMIT 20;

-- 6. Success rate завершившихся jobs.
SELECT
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE status = 'COMPLETED') /
    NULLIF(COUNT(*) FILTER (WHERE status IN ('COMPLETED', 'FAILED', 'CANCELLED')), 0),
    2
  ) AS success_rate_percent
FROM jobs;

-- 7. Последние audit events конкретного пользователя.
SELECT id, action, entity_type, entity_id, outcome, request_id, created_at
FROM audit_events
WHERE actor_user_id = :user_id OR entity_id = CAST(:user_id AS text)
ORDER BY created_at DESC, id
LIMIT 50;

-- 8. Документы с неготовыми индексами и источником.
SELECT d.id, d.normalized_title, s.name AS source, d.bm25_status, d.vector_status
FROM documents AS d
JOIN sources AS s ON s.id = d.source_id
WHERE d.bm25_status IN ('PENDING', 'FAILED', 'NOT_INDEXED', 'OUTDATED')
   OR d.vector_status IN ('PENDING', 'FAILED', 'NOT_INDEXED', 'OUTDATED')
ORDER BY d.last_synced_at DESC, d.id;

-- 9. Документы без сохранённых chunks.
SELECT d.id, d.normalized_title, d.processing_status, d.chunks_count
FROM documents AS d
WHERE NOT EXISTS (
  SELECT 1 FROM document_chunks AS c WHERE c.document_id = d.id
)
ORDER BY d.updated_at DESC, d.id;

-- 10. Среднее и максимум chunks на документ по источникам.
SELECT s.name, ROUND(AVG(stats.chunk_count), 2) AS avg_chunks, MAX(stats.chunk_count) AS max_chunks
FROM sources AS s
JOIN (
  SELECT d.source_id, d.id, COUNT(c.id) AS chunk_count
  FROM documents AS d
  LEFT JOIN document_chunks AS c ON c.document_id = d.id
  GROUP BY d.source_id, d.id
) AS stats ON stats.source_id = s.id
GROUP BY s.id, s.name
ORDER BY avg_chunks DESC, s.id;

-- 11. Processing и deduplication statuses.
SELECT processing_status, deduplication_status, COUNT(*) AS documents_count
FROM documents
GROUP BY processing_status, deduplication_status
ORDER BY processing_status, deduplication_status;

-- 12. Exact duplicates с canonical document.
SELECT duplicate.id, duplicate.external_id, canonical.id AS canonical_id,
       canonical.external_id AS canonical_external_id, duplicate.content_hash
FROM documents AS duplicate
JOIN documents AS canonical ON canonical.id = duplicate.duplicate_of_document_id
WHERE duplicate.deduplication_status = 'EXACT_DUPLICATE'
ORDER BY duplicate.created_at DESC, duplicate.id;

-- 13. История смысловых revisions с номером изменения (оконная функция).
SELECT r.document_id, r.version, r.change_reason, r.created_at,
       ROW_NUMBER() OVER (PARTITION BY r.document_id ORDER BY r.version) AS revision_number
FROM document_revisions AS r
ORDER BY r.document_id, r.version;

-- 14. Документы, изменённые после последней индексации.
SELECT id, normalized_title, source_updated_at, last_indexed_at, bm25_status, vector_status
FROM documents
WHERE last_indexed_at IS NULL OR source_updated_at > last_indexed_at
ORDER BY source_updated_at DESC NULLS LAST, id;

-- 15. Доля ingestion failures по заданиям.
WITH per_job AS (
  SELECT j.id, j.status, j.processed_items, COUNT(f.id) AS failures
  FROM jobs AS j
  LEFT JOIN ingestion_failures AS f ON f.job_id = j.id
  WHERE j.type = 'SOURCE_SYNC'
  GROUP BY j.id, j.status, j.processed_items
)
SELECT id, status, processed_items, failures,
       ROUND(100.0 * failures / NULLIF(processed_items, 0), 2) AS failure_percent
FROM per_job
ORDER BY failure_percent DESC NULLS LAST, id;

-- 16. Накопленные counters и checkpoint источников.
SELECT s.name, state.current_mode, state.next_page, state.last_checkpoint_at,
       state.total_questions_fetched, state.total_answers_fetched,
       state.total_documents_inserted, state.total_documents_updated,
       state.total_documents_unchanged, state.total_exact_duplicates,
       state.total_items_skipped, state.total_errors, state.total_chunks_created
FROM sources AS s
LEFT JOIN source_sync_states AS state ON state.source_id = s.id
ORDER BY s.name, s.id;

-- 17. Answers конкретного document и corpus selection.
SELECT a.external_id, a.author_name, a.score, a.is_accepted,
       a.selected_for_corpus, a.selection_rank, a.source_missing
FROM answers AS a
WHERE a.document_id = :document_id
ORDER BY a.selection_rank NULLS LAST, a.score DESC, a.external_id;

-- 18. Chunks конкретной версии документа.
SELECT ordinal, section_type, token_count, character_count, has_code, content_hash
FROM document_chunks
WHERE document_id = :document_id
ORDER BY document_version DESC, ordinal;

-- 19. Progress и последнее событие активных jobs (LATERAL subquery).
SELECT j.id, j.type, j.status, j.progress, j.heartbeat_at,
       e.level, e.code, e.message, e.created_at
FROM jobs AS j
LEFT JOIN LATERAL (
  SELECT level, code, message, created_at
  FROM job_events
  WHERE job_id = j.id
  ORDER BY created_at DESC
  LIMIT 1
) AS e ON true
WHERE j.status IN ('QUEUED', 'RUNNING')
ORDER BY j.created_at, j.id;

-- 20. Worker heartbeat.
SELECT instance_id, status, current_job_id, heartbeat_at,
       now() - heartbeat_at AS heartbeat_age
FROM worker_instances
ORDER BY heartbeat_at DESC, id
LIMIT 20;
