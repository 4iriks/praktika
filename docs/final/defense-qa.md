# Defense questions and answers

1. **Why Stack Overflow?** It provides attributed, versioned technical threads and an official API. A document is one question plus deterministically selected answers.
2. **Why ≥5000?** It demonstrates corpus-scale ingestion/search rather than a demo seed; acceptance excludes `stage4-*` demo IDs.
3. **How does parsing work?** Pages of questions and batches of up to 100 question IDs for paginated answers are fetched outside DB transactions.
4. **How is backoff respected?** The client enforces local rate limiting, `backoff`, `Retry-After`, jittered bounded retries and cancellation-aware waits.
5. **What is a checkpoint?** The last committed page/window/counters; it advances only after the corresponding data transaction commits.
6. **How is deduplication done?** Unique source/external identity plus canonical SHA-256 exact-content detection; duplicates remain stored but are not indexed.
7. **How is chunking done?** Deterministic section/code-aware packing with token limits and bounded overlap; code indentation is preserved.
8. **What is BM25?** A lexical ranking function using term frequency, inverse document frequency and length normalization.
9. **What is HNSW?** An approximate nearest-neighbor graph used for fast dense cosine retrieval.
10. **BM25 vs Vector?** BM25 favors exact tokens; dense vectors capture semantic similarity. Neither raw score is directly comparable.
11. **How does Hybrid work?** Weighted reciprocal-rank fusion computes `weight/(k+rank)` for each retriever and keeps component evidence.
12. **Why rerank?** A cross-encoder jointly scores query/passage for precision on a smaller candidate set.
13. **What is RAG?** Retrieval selects verified passages before local generation; the answer is stored with its exact sources.
14. **Why no answer without sources?** Configurable retrieval thresholds return deterministic insufficient context without calling the LLM.
15. **How are hallucinations reduced?** Source-only prompt, retrieval thresholds, citation mapping/validation and no tool/code execution.
16. **Why Qdrant?** It supports named dense/sparse vectors, HNSW, payload filters, aliases and atomic blue-green activation.
17. **Why PostgreSQL?** It is the transactional source of truth for identity, corpus, durable jobs, audit and manifests.
18. **Why FastAPI?** Typed async HTTP contracts align with the TypeScript adapter and I/O-heavy services.
19. **Why Ollama/local LLM?** Data stays local, operation is reproducible and no paid cloud dependency is required.
20. **How do roles work?** Sessions resolve user→role→permissions on the server; frontend visibility is only UX.
21. **How are passwords protected?** Argon2id hashes only; plaintext/password hashes never appear in API or audit.
22. **Why HttpOnly cookies and CSRF?** JavaScript cannot read the session token; unsafe cookie-auth requests require a rotated double-submit token.
23. **What is in audit?** Sanitized actor/action/entity/outcome/request ID and safe before/after metadata; no credentials.
24. **How do background jobs work?** PostgreSQL `FOR UPDATE SKIP LOCKED`, lease/heartbeat, retry, cancellation and job events.
25. **How does recovery work?** Expired leases requeue within max attempts and the handler resumes from the committed checkpoint.
26. **How was quality measured?** Reviewed qrels only: Recall, MRR, nDCG, zero-result rate; RAG adds citation/source/refusal measures.
27. **What are the limitations?** Local model latency, API quota, manually reviewed dataset size and derived-index rebuild time.
28. **What next?** More reviewed qrels, measured tuning and incremental operational monitoring without changing the security model.
