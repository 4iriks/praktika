COMPOSE ?= $(shell if docker compose version >/dev/null 2>&1; then \
	printf '%s' 'docker compose'; \
	elif command -v docker-compose >/dev/null 2>&1 && docker-compose version >/dev/null 2>&1; then \
	printf '%s' 'docker-compose'; \
	else \
	printf '%s' 'docker compose'; \
	fi)

.PHONY: backend-up backend-test backend-lint backend-migrate backend-seed backend-logs \
	worker-up worker-logs worker-health sync-smoke sync-incremental ingestion-report \
	sync-full-confirmed qdrant-up indexer-up index-logs index-status index-full \
	models-pull embedding-model-pull llm-model-pull ollama-status ollama-models \
	reranker-up reranker-logs reranker-model-pull search-evaluate rag-evaluate \
	local-model-smoke

backend-up:
	$(COMPOSE) up -d postgres backend

backend-test:
	cd backend && .venv/bin/pytest --cov=app --cov-report=term-missing --cov-fail-under=80

backend-lint:
	cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy app

backend-migrate:
	$(COMPOSE) run --rm backend alembic upgrade head

backend-seed:
	$(COMPOSE) run --rm backend python -m app.scripts.seed_demo

backend-logs:
	$(COMPOSE) logs -f backend postgres

worker-up:
	$(COMPOSE) up -d postgres worker

worker-logs:
	$(COMPOSE) logs -f worker

worker-health:
	$(COMPOSE) run --rm worker python -m app.scripts.worker_health

sync-smoke:
	@test -n "$(SOURCE_ID)" || (echo "Укажите SOURCE_ID=<uuid>" && exit 1)
	$(COMPOSE) run --rm worker python -m app.scripts.enqueue_sync $(SOURCE_ID) \
		--mode INITIAL --max-documents 100 --max-pages 2

sync-incremental:
	@test -n "$(SOURCE_ID)" || (echo "Укажите SOURCE_ID=<uuid>" && exit 1)
	$(COMPOSE) run --rm worker python -m app.scripts.enqueue_sync $(SOURCE_ID) \
		--mode INCREMENTAL --max-pages 2

ingestion-report:
	$(COMPOSE) run --rm worker python -m app.scripts.ingestion_report

qdrant-up:
	$(COMPOSE) up -d qdrant

indexer-up:
	$(COMPOSE) up -d postgres qdrant ollama indexer

index-logs:
	$(COMPOSE) logs -f indexer qdrant ollama

index-status:
	$(COMPOSE) run --rm backend python -m app.scripts.worker_health

index-full:
	@echo "Полная переиндексация запускается из /admin/indexes с явным подтверждением."

embedding-model-pull:
	$(COMPOSE) run --rm backend python -m app.scripts.pull_models --embedding-only

models-pull:
	$(COMPOSE) run --rm backend python -m app.scripts.pull_models

llm-model-pull:
	$(COMPOSE) run --rm backend python -m app.scripts.pull_models --llm-only

ollama-status:
	$(COMPOSE) exec ollama ollama ps

ollama-models:
	$(COMPOSE) exec ollama ollama list

reranker-up:
	$(COMPOSE) up -d reranker

reranker-logs:
	$(COMPOSE) logs -f reranker

reranker-model-pull:
	$(COMPOSE) run --rm reranker python -m app.scripts.pull_reranker

search-evaluate:
	$(COMPOSE) run --rm backend python -m app.scripts.evaluate_retrieval

rag-evaluate:
	$(COMPOSE) run --rm backend python -m app.scripts.evaluate_rag

local-model-smoke:
	@test "$(RUN_LIVE_LOCAL_MODELS)" = "1" || \
		(echo "Live model smoke не запущен: RUN_LIVE_LOCAL_MODELS=1" && exit 1)
	$(COMPOSE) run --rm -e RUN_LIVE_LOCAL_MODELS=1 backend \
		python -m app.scripts.live_local_models_smoke

sync-full-confirmed:
	@test "$(CONFIRM_FULL_SYNC)" = "YES" || \
		(echo "Полный импорт не запущен. Требуется CONFIRM_FULL_SYNC=YES" && exit 1)
	@test -n "$(SOURCE_ID)" || (echo "Укажите SOURCE_ID=<uuid>" && exit 1)
	$(COMPOSE) run --rm -e CONFIRM_FULL_SYNC=YES worker \
		python -m app.scripts.enqueue_sync $(SOURCE_ID) --mode INITIAL
