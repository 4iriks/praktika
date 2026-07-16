# Presentation speaker notes

1. Introduce PyAnswer in one sentence and identify the individual author.
2. Explain why lexical-only or LLM-only answers are insufficient.
3. Emphasize measurable criteria and that live `NOT_RUN` is never presented as success.
4. Explain the thread/document definition and preserved attribution.
5. Walk left-to-right through the same-origin architecture; PostgreSQL is authoritative.
6. Mention answer batching, anonymous API 25-page windows, checkpoint-after-commit and resume.
7. Group entities rather than reading every column; point out N:M and self-references.
8. Explain sparse BM25 versus dense HNSW and atomic alias switching.
9. State the RRF formula `w/(k+rank)` and why raw scores cannot be added.
10. Explain source selection, context budget, insufficient context and citation validation.
11. Show server-side permissions; UI role hiding is not the security boundary.
12. Follow the short demo script and keep a captured fallback only if clearly labelled.
13. Read values from generated artifacts, including timestamp/index/dataset hashes.
14. Mention Argon2id, HttpOnly sessions, CSRF, audit sanitization and restore validation.
15. End with proven results and limitations; invite questions.
