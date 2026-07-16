COMPOSE ?= $(shell if docker compose version >/dev/null 2>&1; then \
	printf '%s' 'docker compose'; \
	elif command -v docker-compose >/dev/null 2>&1 && docker-compose version >/dev/null 2>&1; then \
	printf '%s' 'docker-compose'; \
	else \
	printf '%s' 'docker compose'; \
	fi)

.PHONY: backend-up backend-test backend-lint backend-migrate backend-seed backend-logs \
	worker-up worker-logs worker-health

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
	$(COMPOSE) ps worker
	$(COMPOSE) exec -T postgres sh -c 'psql --no-psqlrc -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" \
		-c "SELECT instance_id, status, current_job_id, heartbeat_at, now() - heartbeat_at AS heartbeat_age FROM worker_instances ORDER BY heartbeat_at DESC LIMIT 5"'
