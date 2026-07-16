# Управление моделями

Embedding model: `qwen3-embedding:0.6b`, 1024 dimensions. Document embeddings получают неизменённый `contextual_text`; query instruction сохранён в configuration hash и будет применяться только к запросам в 6.2.

```bash
make embedding-model-pull
docker-compose exec ollama ollama list
```

Ollama volume `ollama_models` постоянный. Model pull всегда явный. Для GPU:

```bash
docker-compose -f compose.yaml -f compose.gpu.yaml up -d ollama indexer
```

При отсутствии модели system/index API честно показывает `model missing`; job не выставляет READY.
