# Ollama

PyAnswer использует native Ollama API: `/api/embed` для `qwen3-embedding:0.6b` и `/api/chat`
для `qwen3:8b`. Для chat всегда передаются `stream=true` и `think=false`; thinking не отправляется
в UI и не сохраняется. `keep_alive`, context, temperature, output limit и timeout задаются env.

Модели не скачиваются при build, migration, test или startup:

```bash
make ollama-up
make embedding-model-pull
make llm-model-pull
# либо обе модели
make models-pull
make ollama-status
make ollama-models
```

Ollama использует persistent `ollama_models`, доступен backend/indexer только во внутренней сети
Compose и не публикуется браузеру. Base Compose работает на CPU. `compose.gpu.yaml` включает
NVIDIA device reservation; для RTX 3080 Ti рекомендуются `OLLAMA_MAX_LOADED_MODELS=2`,
`OLLAMA_NUM_PARALLEL=1` и ограниченная RAG queue. Реальное потребление VRAM зависит от context,
quantization и runtime и должно измеряться smoke-тестом, а не предполагаться.

`MODEL_MISSING`, timeout, overload и недоступность Ollama преобразуются в безопасные 503/504.
Модель можно выгрузить через Ollama API/CLI; сокращение `LLM_NUM_CTX` уменьшает расход памяти.
