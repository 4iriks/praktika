# ERD explanation

- `roles`, `permissions`, `role_permissions`, `users`, `sessions`, `user_preferences` implement
  identity, server sessions and N:M RBAC. Session tokens are stored only as hashes.
- `sources` has one `source_sync_states` checkpoint and many `documents`/`jobs`.
- `documents` owns `answers`, N:M `tags` through `document_tags`, immutable revisions and current
  version chunks. `duplicate_of_document_id` is a self-reference.
- `jobs` is a durable queue; `retry_of_job_id` is a self-reference, `worker_instances` claims work,
  while `job_events` and `ingestion_failures` preserve operational evidence.
- `search_index_versions` describes physical Qdrant collections; `search_index_entries` maps
  PostgreSQL chunks to deterministic points. Vectors remain derived data.
- `search_runs` stores safe telemetry. `rag_responses` and `rag_response_sources` persist grounded
  answers and citation mapping without hidden reasoning.
- `search_history`, `saved_documents`, `feedback`, `audit_events` and `system_settings` implement
  user and administrative contours. Audit has no public update/delete API.

Cardinality, PK/FK, unique constraints and self-references are shown in [the ERD](../erd.md).
