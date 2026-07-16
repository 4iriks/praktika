# PyAnswer — practice report source

> Title page placeholders: institution, department, student name/group, supervisor, city, year.
> Do not copy numbers into this document manually; cite generated files under `artifacts/`.

## Contents

The final DOCX table of contents is generated from the headings below.

## 1. Introduction

PyAnswer is a local Russian-language Python knowledge system combining reproducible ingestion,
hybrid retrieval and retrieval-grounded generation.

## 2. Goal and practice tasks

Build a role-aware system that ingests at least 5000 real threads, searches them lexically and
semantically, and produces cited local answers without paid cloud APIs.

## 3. Domain analysis

Programming questions contain precise identifiers and semantic paraphrases. This motivates both
BM25 and dense retrieval, followed by reranking.

## 4. System requirements

See [traceability](requirements-traceability.md). Security, durability and honest failure states
are first-class requirements.

## 5. Data source

Stack Overflow на русском, site `ru.stackoverflow`, tag `python`; attribution and source URLs are
preserved. Quota/backoff and checkpointing are respected.

## 6. PyAnswer architecture

Browser → Nginx/React → FastAPI → PostgreSQL/Qdrant/Ollama; ingestion and indexing run in separate
leased workers. PostgreSQL is the source of truth.

## 7. Database and ERD

See [ERD](../erd.md) and [entity explanation](erd-explanation.md).

## 8. Server authorization and roles

Opaque HttpOnly sessions, Argon2id, CSRF and server-side USER/EDITOR/ADMIN permission checks are
implemented; browser storage never contains an access token.

## 9. Stack Exchange parser and normalization

The typed async client fetches question pages and answer batches, honors `has_more`, quota,
Retry-After and backoff. Parser-based HTML cleaning preserves fenced code.

## 10. Deduplication, revisions and chunking

Identity and exact SHA-256 content deduplication are deterministic. Changed canonical content
creates a revision and code-aware chunks; metadata-only changes do not churn chunks.

## 11. Background jobs

PostgreSQL `SKIP LOCKED`, lease, heartbeat, checkpoint, cancellation, retry and stale recovery make
SOURCE_SYNC and indexing restart-safe.

## 12. BM25, HNSW, hybrid retrieval and reranking

Qdrant stores named sparse BM25 and 1024-dimensional dense cosine vectors. Weighted RRF combines
incompatible raw score spaces; a pinned local cross-encoder reranks top candidates.

## 13. Local LLM and RAG

Ollama `qwen3:8b` receives only numbered trusted context. Insufficient context prevents generation;
citations are assigned and validated by the backend and thinking is never exposed.

## 14. User interface and Docker deployment

React supports guest/user/editor/admin flows. Production assets and `/api` share Nginx origin
`http://localhost:8080`; SSE buffering is disabled only for the RAG stream.

## 15. Testing and quality evaluation

Use `make verify-all`. Search/RAG/performance values must be copied from generated evaluation
reports after reviewed datasets and live services are available.

## 16. Performance, security and resilience

Reports cover latency, resource limits, failures, dependency audits, backup and restore checks.
Unavailable metrics remain `UNKNOWN`/`NOT_RUN`.

## 17. Results, limitations and future work

Actual corpus/index/model counts and acceptance status come from corpus/release manifests. Possible
future work includes larger reviewed qrels and model-specific tuning, not cloud replacement.

## 18. Conclusion

PyAnswer demonstrates an end-to-end local retrieval and cited generation architecture with
auditable data provenance and failure behavior.

## Sources and appendices

Append API contract, [read-only SQL](sql-demo.md), Docker configuration, screenshots, test reports,
evaluation reports and the [demo script](demo-script.md).
