# Hybrid ranking

BM25 и cosine scores несопоставимы и напрямую не суммируются. PyAnswer использует weighted Reciprocal Rank Fusion:

`RRF(d) = w_bm25 / (k + rank_bm25) + w_vector / (k + rank_vector)`

По умолчанию `k=60`, оба веса равны `1`. Отсутствующий component получает `null`, а не искусственный zero. Tie-break: fusion DESC, лучший component rank, стабильный point UUID. После fusion top candidates передаются reranker; итог при успешном reranker: `0.85 * reranker + 0.15 * normalized_fusion`. При необязательном недоступном reranker выдаётся честный fusion-only fallback.
