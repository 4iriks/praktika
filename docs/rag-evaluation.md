# RAG evaluation

`backend/evaluation/rag.jsonl` содержит 20 вручную заданных вопросов: expected source external
IDs, ключевые пункты и контроль insufficient-context. Cloud/LLM judge не используется.

```bash
cd backend
python -m app.scripts.evaluate_rag --base-url http://127.0.0.1:8000/api
```

CLI формирует JSON и Markdown с dataset hash, source recall, citation validity, key-point
coverage, insufficient-context accuracy и latency p50/p95. Это opt-in operational evaluation:
нужны поднятые Qdrant, index, reranker и локальная модель. Обычные tests проверяют расчёт метрик
без сети и моделей. Результаты нельзя считать объективной оценкой полноты ответа; labels требуют
ручной ревизии после изменения корпуса.
