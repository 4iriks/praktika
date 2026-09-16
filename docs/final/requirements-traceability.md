# Requirements traceability

The generated `artifacts/acceptance-report.*` is authoritative for live status. A code path is not
evidence that its live dependency passed.

| Requirement | Status | Implementation | Test/evidence | Limitation |
|---|---|---|---|---|
| Stack Exchange parser | implemented | `app/integrations/stackexchange`, `app/workers/source_sync.py` | Stage 5 tests; corpus manifest | Live count comes only from manifest |
| ≥5000 real documents | passed | durable `SOURCE_SYNC` | 10 700 real CHUNKED documents in acceptance/corpus reports | Demo IDs are excluded; 25k import continues by checkpoint |
| PostgreSQL/Alembic | implemented | `app/db`, `alembic/` | migration and integration tests | Requires live DB |
| BM25 + HNSW | implemented | named sparse/dense Qdrant vectors | index consistency report | Requires active alias |
| Hybrid/RRF/top-N/scores | implemented | `app/services/search.py`, `app/search/fusion.py` | search tests/evaluation | Metrics only on reviewed qrels |
| Source URL/attribution | implemented | documents/answers schemas | data consistency check | Missing attribution is a failure |
| Local RAG/Ollama/citations | implemented | `app/services/rag.py`, `app/rag/` | RAG tests/evaluation | Live model smoke is separate |
| Reranker/filters | implemented | internal reranker service/search filters | Stage 6 tests | Fallback is explicit |
| React UI and HTTP mode | implemented | `frontend/src`, same-origin `/api` | 103 Vitest tests and live HTTP acceptance | Playwright suite is not implemented |
| Registration/three roles/RBAC | passed | auth services/permission matrix | integration tests and live USER/EDITOR/ADMIN login/logout | Full browser matrix remains manual |
| Audit/background jobs | implemented | audit models; PostgreSQL queue | integration tests | Audit is public-API read-only |
| Dedup/chunking/revisions | implemented | processing/ingestion services | Stage 5 tests | Exact duplicates are retained |
| Docker/Nginx/GPU override | implemented | `compose*.yaml`, `frontend/nginx.conf` | Compose config/build | GPU remains optional |
| Backup/restore check | implemented | `scripts/backup.py`, `restore_check.py` | backup manifest/checksums | Main volumes are never overwritten |
| ERD and SQL JOIN/GROUP/subquery | implemented | `docs/erd.md`, `docs/final/sql-demo.sql` | manual/read-only | Names follow latest migration |
| Reproducible start | implemented | `make first-run`, `make demo-up` | `make verify-all` | Models/full import require consent |
| Report/presentation/video | implemented | `docs/final/` | documentation review | Numeric results reference artifacts |
| Individual contribution | pending confirmation | `docs/final/contribution.md` | author confirmation | No unsupported percentage is stated |
