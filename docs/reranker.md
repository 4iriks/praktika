# Local reranker

Reranker работает отдельным внутренним FastAPI-сервисом, не внутри основного backend. Модель закреплена как `Qwen/Qwen3-Reranker-0.6B`, revision `1f54aa72c421b677caa56ece526856f8c60144a5`, runtime `sentence-transformers==5.4.0`. Base Compose использует CPU, чтобы оставить VRAM локальным embedding и generation моделям Ollama.

CPU demo-профиль ограничивает rerank окном из 8 passages и 768 токенами на passage. Эти значения можно увеличить через `RERANKER_TOP_N` и `RERANKER_MAX_LENGTH`, если приоритетом является качество, а не интерактивная задержка.

Модель не скачивается при build/tests/start. Явная команда: `make reranker-model-pull`. При `RERANKER_REQUIRED=true` outage даёт 503; при false поиск продолжает fusion-only без выдуманного score.
