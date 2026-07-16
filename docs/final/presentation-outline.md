# Presentation outline (12–15 slides)

| # | Title | 3–5 points | Visual | Time |
|---:|---|---|---|---:|
| 1 | PyAnswer | topic; author placeholder; local Python knowledge system | home screenshot | 20 s |
| 2 | Problem | exact terms; semantic paraphrases; hallucinations | problem triangle | 35 s |
| 3 | Requirements | ≥5000 real docs; three roles; local models; 35 GB | checklist | 35 s |
| 4 | Data source | ru.stackoverflow; python; attribution; quota | source page | 35 s |
| 5 | Architecture | Nginx; FastAPI; PostgreSQL; workers; Qdrant/Ollama | architecture diagram | 50 s |
| 6 | Ingestion | pagination/windows; answers batch; checkpoint; retries | pipeline | 45 s |
| 7 | Database | identity/content/jobs/index/RAG groups | ERD | 45 s |
| 8 | Search indexes | BM25; dense cosine/HNSW; versioned alias | index diagram | 45 s |
| 9 | Hybrid + reranker | weighted RRF; component scores; cross-encoder | score UI | 45 s |
| 10 | RAG | retrieval only; insufficient context; citations; no thinking | answer screenshot | 50 s |
| 11 | UI and roles | USER; EDITOR; ADMIN; RBAC/audit | three screenshots | 40 s |
| 12 | Demo | search; cited answer; hide/reindex; system | demo route | 30 s |
| 13 | Metrics | corpus/index/evaluation/latency from artifacts | real charts | 40 s |
| 14 | Reliability/security | sessions; CSRF; backups; failure modes | shield diagram | 35 s |
| 15 | Result | achieved items; honest limits; next work | final checklist | 30 s |
