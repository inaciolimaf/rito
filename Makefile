.PHONY: up down migrate seed dev test lint

up:
	docker compose up -d --wait
	docker compose exec -T postgres psql -U rito -d rito -tc \
		"SELECT 1 FROM pg_database WHERE datname = 'rito_test'" | grep -q 1 || \
		docker compose exec -T postgres psql -U rito -d rito -c "CREATE DATABASE rito_test OWNER rito"

down:
	docker compose down

migrate:
	cd backend && uv run alembic upgrade head

seed:
	cd backend && uv run python -m app.core.seed

dev:
	$(MAKE) -j2 dev-backend dev-frontend

dev-backend:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

test:
	@bash scripts/run-tests.sh

lint:
	cd backend && uv run ruff check . && uv run black --check . && uv run mypy .
	cd frontend && npm run lint
