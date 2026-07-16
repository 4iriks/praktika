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
