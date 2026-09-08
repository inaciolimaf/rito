.PHONY: up down migrate seed dev test test-backend test-frontend test-e2e test-nightly test-mutation seed-volume drop-volume lint

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

test-backend:
	cd backend && MIGRATIONS_DATABASE_URL="$${TEST_MIGRATIONS_DATABASE_URL:-$$MIGRATIONS_DATABASE_URL}" uv run alembic upgrade head
	cd backend && uv run pytest -n auto $(if $(PYTEST_ALLOW_HOSTS),--allow-hosts=$(PYTEST_ALLOW_HOSTS))

test-frontend:
	cd frontend && npm run test

test-e2e:
	cd e2e && npm test

# Spec 098, regra 10: perfilamento com volume real. Fora do CI de PR — o seed são
# 1,95 milhão de linhas e o orçamento do PR é de 300 s para a suíte inteira.
#
# O alvo SEMEIA, MEDE e LIMPA. As três coisas juntas de propósito: 1,95 milhão de linhas
# esquecidas no `rito_test` mudam o tamanho das tabelas que a suíte de PR compartilha, e
# o teste de p95 da busca (spec 096, com 20 mil contatos próprios) passou a falhar por
# causa disso. Volume de perfilamento é estado de uma execução, não do banco.
seed-volume:
	cd backend && uv run python scripts/volume_seed.py

drop-volume:
	cd backend && uv run python scripts/volume_seed.py --drop

test-nightly: seed-volume
	@( cd backend && uv run pytest -m nightly -p no:randomly \
		$(if $(PYTEST_ALLOW_HOSTS),--allow-hosts=$(PYTEST_ALLOW_HOSTS)) ); \
		status=$$?; $(MAKE) drop-volume; exit $$status

# Spec 132. Teste de mutação SOB DEMANDA — nunca no `make test` (CLAUDE.md §3): um módulo
# custa minutos e o orçamento das três suítes é de 300 s. Fora do CI de PR e fora do
# nightly, porque o vermelho dele precisa de classificação humana (§9.7 da spec 132).
#
#   make test-mutation MODULE=app/domain/ai/sql_guard.py TESTS=tests/unit/test_sql_guard.py
#
# TESTS é a suíte rápida (roda por mutante); CONFIRM_TESTS, opcional, é a suíte larga que
# reconfere cada sobrevivente antes de ele virar linha do relatório.
test-mutation:
	@test -n "$(MODULE)" || { echo "uso: make test-mutation MODULE=app/... TESTS=tests/..."; exit 2; }
	@test -n "$(TESTS)" || { echo "uso: make test-mutation MODULE=app/... TESTS=tests/..."; exit 2; }
	@work=$$(mktemp -d); \
		rsync -a --exclude '__pycache__' --exclude '.pytest_cache' \
			backend/app backend/tests backend/alembic backend/scripts "$$work/"; \
		cp backend/pyproject.toml backend/alembic.ini backend/.python-version "$$work/"; \
		[ -f backend/.env ] && cp backend/.env "$$work/"; \
		ln -s "$(CURDIR)/backend/.venv" "$$work/.venv"; \
		( cd "$$work" && ./.venv/bin/python -m scripts.mutation --root "$$work" \
			--module $(MODULE) --tests $(TESTS) \
			$(if $(CONFIRM_TESTS),--confirm-tests $(CONFIRM_TESTS)) ); \
		status=$$?; rm -rf "$$work"; exit $$status

lint:
	cd backend && uv run ruff check . && uv run black --check . && uv run mypy .
	cd frontend && npm run lint
