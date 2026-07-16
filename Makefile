.PHONY: backend-up backend-test backend-lint backend-migrate backend-seed backend-logs

backend-up:
	docker compose up -d postgres backend

backend-test:
	cd backend && .venv/bin/pytest --cov=app --cov-report=term-missing --cov-fail-under=80

backend-lint:
	cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy app

backend-migrate:
	docker compose run --rm backend alembic upgrade head

backend-seed:
	docker compose run --rm backend python -m app.scripts.seed_demo

backend-logs:
	docker compose logs -f backend postgres
