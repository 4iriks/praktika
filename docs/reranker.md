# Local reranker

Reranker работает отдельным внутренним FastAPI-сервисом, не внутри основного backend. Модель закреплена как `Qwen/Qwen3-Reranker-0.6B`, revision `e1775d95f8cf4625eea7879c6edb34beae6c42af`, runtime `sentence-transformers==5.4.0`. Base Compose использует CPU; GPU override включает CUDA.

Модель не скачивается при build/tests/start. Явная команда: `make reranker-model-pull`. При `RERANKER_REQUIRED=true` outage даёт 503; при false поиск продолжает fusion-only без выдуманного score.
