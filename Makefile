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
	local-model-smoke first-run demo-up demo-down demo-restart demo-status demo-logs \
	demo-check demo-reset models-check import-smoke import-minimum import-full import-dump \
	evaluate e2e backup restore-check disk-report data-check index-check corpus-manifest \
	release-manifest verify-all cleanup-safe

ARTIFACT_RUN = $(COMPOSE) run --rm --no-deps \
	-v $(CURDIR):/workspace/repo:ro -v $(CURDIR)/artifacts:/app/artifacts \
	-e REPO_ROOT=/workspace/repo -e ARTIFACTS_DIR=/app/artifacts backend

first-run:
	@command -v docker >/dev/null || (echo "Docker не найден" && exit 1)
	@$(COMPOSE) version >/dev/null
	@test -f .env || python3 scripts/generate-local-env.py
	@df -Pk . | awk 'NR == 2 && $$4 < 5242880 {print "Недостаточно свободного места (<5 GiB)"; exit 2}'
	$(COMPOSE) up -d postgres qdrant ollama
	$(COMPOSE) run --rm --no-deps backend alembic upgrade head
	$(COMPOSE) run --rm --no-deps backend python -m app.scripts.bootstrap
	$(COMPOSE) run --rm --no-deps -e SEED_DEMO_DATA=true backend python -m app.scripts.seed_demo
	@$(COMPOSE) exec ollama ollama list || true
	$(COMPOSE) up -d backend worker indexer reranker frontend
	@echo "PyAnswer: http://localhost:$${FRONTEND_PORT:-8080}"
	@echo "Большие модели и полный импорт автоматически не запускаются."

demo-up:
	@test -f .env || python3 scripts/generate-local-env.py
	$(COMPOSE) up -d postgres qdrant ollama backend worker indexer reranker frontend

demo-down:
	$(COMPOSE) down

demo-restart:
	$(COMPOSE) restart backend worker indexer reranker frontend

demo-status:
	$(COMPOSE) ps

demo-logs:
	$(COMPOSE) logs -f --tail=200 frontend backend worker indexer reranker

models-check:
	$(COMPOSE) exec ollama ollama list

import-smoke: sync-smoke

import-minimum:
	@test "$(RUN_LIVE_MINIMUM_IMPORT)" = "1" || \
		(echo "Требуется RUN_LIVE_MINIMUM_IMPORT=1" && exit 1)
	@test -n "$(SOURCE_ID)" || (echo "Укажите SOURCE_ID=<uuid>" && exit 1)
	$(COMPOSE) run --rm --no-deps worker python -m app.scripts.enqueue_sync $(SOURCE_ID) \
		--mode INITIAL --max-documents 5000 --max-pages 60

import-full:
	@test "$(RUN_FULL_IMPORT)" = "1" || (echo "Требуется RUN_FULL_IMPORT=1" && exit 1)
	@test -n "$(SOURCE_ID)" || (echo "Укажите SOURCE_ID=<uuid>" && exit 1)
	$(COMPOSE) run --rm --no-deps -e CONFIRM_FULL_SYNC=YES worker \
		python -m app.scripts.enqueue_sync $(SOURCE_ID) --mode INITIAL

import-dump:
	@test "$(RUN_DATA_DUMP_IMPORT)" = "1" || \
		(echo "Требуется RUN_DATA_DUMP_IMPORT=1" && exit 1)
	@test -n "$(DUMP_ARCHIVE)" || \
		(echo "Укажите DUMP_ARCHIVE=/path/to/ru.stackoverflow.com.7z" && exit 1)
	@test -f "$(DUMP_ARCHIVE)" || (echo "Архив не найден: $(DUMP_ARCHIVE)" && exit 1)
	$(COMPOSE) run --rm --no-deps --user "$(shell id -u):$(shell id -g)" \
		-v "$(CURDIR)/artifacts:/app/artifacts" -e ARTIFACTS_DIR=/app/artifacts \
		-v "$(abspath $(DUMP_ARCHIVE)):/data/ru.stackoverflow.com.7z:ro" worker \
		python -m app.scripts.import_stackexchange_dump /data/ru.stackoverflow.com.7z \
		--target-total "$${DUMP_TARGET_TOTAL:-25000}" \
		--concurrency "$${DUMP_IMPORT_CONCURRENCY:-4}" \
		$(if $(filter 1,$(DUMP_REPAIR_ANSWER_GAPS)),--repair-answer-gaps,--max-failures 25)

corpus-manifest:
	$(ARTIFACT_RUN) python -m app.scripts.corpus_manifest

release-manifest:
	$(ARTIFACT_RUN) python -m app.scripts.release_manifest

data-check:
	$(ARTIFACT_RUN) python -m app.scripts.data_consistency_check

index-check:
	$(ARTIFACT_RUN) python -m app.scripts.index_consistency_check

disk-report:
	$(ARTIFACT_RUN) python -m app.scripts.disk_report

demo-check:
	$(ARTIFACT_RUN) python -m app.scripts.acceptance_check

evaluate: search-evaluate rag-evaluate

e2e:
	@test "$(RUN_E2E)" = "1" || (echo "Требуется RUN_E2E=1" && exit 1)
	cd frontend && npm run e2e

backup:
	python3 scripts/backup.py

restore-check:
	@test -n "$(BACKUP_PATH)" || (echo "Укажите BACKUP_PATH=backups/<timestamp>" && exit 1)
	python3 scripts/restore_check.py $(BACKUP_PATH)

demo-reset:
	@test "$(CONFIRM_DEMO_RESET)" = "YES" || \
		(echo "Сброс запрещён без CONFIRM_DEMO_RESET=YES; volumes не удалены" && exit 1)
	@echo "Автоматическое удаление production-like volumes не реализовано."

cleanup-safe:
	@test "$(CONFIRM_CLEANUP)" = "YES" || \
		(echo "Требуется CONFIRM_CLEANUP=YES" && exit 1)
	rm -rf frontend/dist frontend/.vite backend/.pytest_cache backend/.mypy_cache backend/.ruff_cache

verify-all:
	cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check .
	cd backend && .venv/bin/mypy app
	cd backend && .venv/bin/pytest --cov=app --cov-report=term-missing --cov-fail-under=80
	cd frontend && npm run typecheck && npm run lint && npm run test -- --run
	cd frontend && npm run build && npm run format:check
	$(COMPOSE) config --quiet
	$(COMPOSE) -f compose.yaml -f compose.gpu.yaml config --quiet
	$(COMPOSE) build backend worker indexer frontend
	$(COMPOSE) run --rm --no-deps backend alembic check
	$(MAKE) data-check
	$(MAKE) disk-report

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
	@test "$${CONFIRM_INDEX_FULL:-}" = "YES" || (echo "Задайте CONFIRM_INDEX_FULL=YES" && exit 2)
	$(COMPOSE) run --rm -e CONFIRM_INDEX_FULL=YES backend python -m app.scripts.enqueue_full_reindex

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
