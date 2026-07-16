# Retrieval evaluation

`backend/evaluation/retrieval.jsonl` содержит 30 вручную проверяемых запросов и отдельные development/validation splits. Команда `python -m app.scripts.evaluate_retrieval` сравнивает BM25, vector, hybrid и hybrid+reranker и пишет JSON/Markdown.

Метрики: Recall@5/10, MRR@10, nDCG@10, HitRate@5, latency p50/p95. Dataset hash, index/model revisions и timestamp попадают в отчёт. Модели не скачиваются автоматически; результат не утверждает, что hybrid всегда лучше.
