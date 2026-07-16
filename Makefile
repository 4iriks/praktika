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
	models-pull embedding-model-pull

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

models-pull embedding-model-pull:
	$(COMPOSE) run --rm backend python -m app.scripts.pull_models --embedding-only

sync-full-confirmed:
	@test "$(CONFIRM_FULL_SYNC)" = "YES" || \
		(echo "Полный импорт не запущен. Требуется CONFIRM_FULL_SYNC=YES" && exit 1)
	@test -n "$(SOURCE_ID)" || (echo "Укажите SOURCE_ID=<uuid>" && exit 1)
	$(COMPOSE) run --rm -e CONFIRM_FULL_SYNC=YES worker \
		python -m app.scripts.enqueue_sync $(SOURCE_ID) --mode INITIAL
