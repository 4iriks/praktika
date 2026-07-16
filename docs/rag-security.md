# RAG security

- Ollama и reranker internal-only; frontend обращается только к FastAPI.
- Cookie auth, CSRF, guest policy и отдельные rate limits применяются до inference.
- Query, HTML, code и retrieved documents недоверенные; ничего не исполняется.
- Context проходит PostgreSQL visibility/version recheck и trusted source host validation.
- Raw HTML, vectors, credentials, secrets, cookies, prompt и reasoning не возвращаются.
- Citation parser допускает только заранее назначенные `[1]..[N]`; invalid markers удаляются и
  отражаются в `citationValidationPassed=false`.
- Source link открывается только через существующий confirmation UI; trusted source ограничен
  доменом configured source.
- Bounded context/output/queue/concurrency предотвращают неограниченный расход памяти.

Обязательные tests покрывают injection в document/code, forged citation, CSRF, guest policy,
timeout/cancellation, no-thinking stream и отсутствие secret leakage.
