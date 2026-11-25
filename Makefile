# Rito — comandos principais. `make` sem alvo lista os comandos.
.DEFAULT_GOAL := help
# Variáveis que o CI sobrescreve (ou que o dev passa na linha de comando).
COV_DIR ?= /tmp/rito-cov
COVERAGE_WORKERS ?= 3
REQS_FILE ?= /tmp/rito-reqs.txt
E2E_ARGS ?=
CI_WALL_CLOCK_BUDGET ?= 300

.PHONY: help up down migrate seed dev dev-backend dev-frontend test test-backend test-frontend test-e2e test-nightly test-mutation seed-volume drop-volume lint docs coverage types openapi \
	build dup audit install-backend install-frontend install-e2e e2e-browsers \
	coverage-backend coverage-frontend coverage-summary-backend coverage-summary-frontend \
	docker-image image-smoke ci-db ci-minio ci-gate \
	api-types api-types-check bundle

help: ## Lista os comandos disponíveis
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

up: ## Sobe Postgres, Redis e MinIO e cria o banco de teste
	docker compose up -d --wait
	docker compose exec -T postgres psql -U rito -d rito -tc \
		"SELECT 1 FROM pg_database WHERE datname = 'rito_test'" | grep -q 1 || \
		docker compose exec -T postgres psql -U rito -d rito -c "CREATE DATABASE rito_test OWNER rito"

down: ## Derruba os serviços locais
	docker compose down

migrate: ## Aplica as migrações no banco de desenvolvimento
	cd backend && uv run alembic upgrade head

seed: ## Carrega os dados iniciais
	cd backend && uv run python -m app.core.seed

dev: ## Sobe backend e frontend em modo de desenvolvimento
	$(MAKE) -j2 dev-backend dev-frontend

dev-backend: ## Só a API, com recarga automática
	cd backend && uv run uvicorn app.main:app --reload --port 8000

dev-frontend: ## Só o frontend (Vite)
	cd frontend && npm run dev

test: ## As três suítes em paralelo, com o teto de 300 s
	@bash scripts/run-tests.sh

test-backend: ## Suíte do backend (pytest, paralela)
	cd backend && MIGRATIONS_DATABASE_URL="$${TEST_MIGRATIONS_DATABASE_URL:-$$MIGRATIONS_DATABASE_URL}" uv run alembic upgrade head
	cd backend && uv run pytest -n auto $(if $(PYTEST_ALLOW_HOSTS),--allow-hosts=$(PYTEST_ALLOW_HOSTS))

test-frontend: ## Suíte do frontend (vitest)
	cd frontend && npm run test

test-e2e: ## Suíte e2e (Playwright); E2E_ARGS passa flags, ex.: --shard=1/2
	cd e2e && npm test $(if $(E2E_ARGS),-- $(E2E_ARGS))

# Spec 098, regra 10: perfilamento com volume real. Fora do CI de PR — o seed são
# 1,95 milhão de linhas e o orçamento do PR é de 300 s para a suíte inteira.
#
# O alvo SEMEIA, MEDE e LIMPA. As três coisas juntas de propósito: 1,95 milhão de linhas
# esquecidas no `rito_test` mudam o tamanho das tabelas que a suíte de PR compartilha, e
# o teste de p95 da busca (spec 096, com 20 mil contatos próprios) passou a falhar por
# causa disso. Volume de perfilamento é estado de uma execução, não do banco.
seed-volume: ## Semeia o volume de perfilamento (fora do PR)
	cd backend && uv run python scripts/volume_seed.py

drop-volume: ## Remove o volume de perfilamento
	cd backend && uv run python scripts/volume_seed.py --drop

test-nightly: seed-volume ## Perfilamento com volume real: semeia, mede e limpa
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
test-mutation: ## Mutação sob demanda: MODULE= e TESTS= obrigatórios
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

# Teste de mutação (backend/tools/mutation.py, docs/mutation-testing.md): só as funções que o
# diff tocou, nos módulos de [tool.mutation].paths. Falha abaixo do mínimo da faixa ou com
# os testes do mutmut passando de 5 s. `make mutation-all` cobre todos os arquivos (até 40 min).
mutation: ## Mutação das funções alteradas desde origin/main; falha abaixo do mínimo da faixa
	cd backend && timeout 600 uv run python -m tools.mutation

mutation-all: ## Mutação de todos os arquivos de [tool.mutation].paths (no máximo 40 min)
	cd backend && timeout 2400 uv run python -m tools.mutation --all --survivors mutants-survivors.md

lint: ## Lint e formatação do backend e do frontend, com tamanho e fronteiras
	cd backend && uv run ruff check . && uv run black --check . && uv run mypy .
	cd backend && uv run python -m tools.function_size && uv run lint-imports
	cd frontend && npm run lint

docs: ## Documentação de docs/system/ cobre o código e não cita o que sumiu
	cd backend && uv run python -m tools.docs_coverage

coverage: ## Backend com cobertura: falha abaixo do piso de backend/pyproject.toml
	cd backend && COVERAGE_CORE=sysmon uv run pytest -n auto -q --cov

types: ## Checagem de tipos estrita (mypy) do backend
	cd backend && uv run mypy .

openapi: ## Gera backend/openapi.json (contrato da API)
	cd backend && uv run python -m tools.openapi

# --- CI ----------------------------------------------------------------------
# Cada passo do .github/workflows/ci.yml é um alvo daqui (CLAUDE.md §10). Os alvos
# `install-*`, `ci-*` e `docker-*` existem para o CI; localmente são úteis, mas não obrigatórios.
# Relatórios de cobertura vão para COV_DIR (fora do checkout) e o piso mora na config de cada suíte.

build: ## Build de produção do frontend e gate de tamanho do bundle
	cd frontend && npm run build
	cd frontend && npm run bundle:check

dup: ## Gate de duplicação (jscpd, teto em .jscpd.json)
	cd frontend && npm run dup:check

audit: ## Auditoria de dependências: pip-audit (backend) e npm audit (frontend)
	cd backend && uv export --no-dev --no-emit-project --format requirements-txt > $(REQS_FILE)
	cd backend && uv run --with pip-audit pip-audit --strict -r $(REQS_FILE)
	cd frontend && npm audit --audit-level=high

install-backend: ## Instala as dependências do backend pelo uv.lock
	cd backend && uv sync --frozen

install-frontend: ## Instala as dependências do frontend pelo package-lock.json
	cd frontend && npm ci --no-audit --no-fund

install-e2e: ## Instala as dependências do e2e pelo package-lock.json
	cd e2e && npm ci --no-audit --no-fund

e2e-browsers: ## Chromium do Playwright com as bibliotecas de sistema
	cd e2e && npx playwright install --with-deps chromium

coverage-backend: ## Cobertura do backend (passo de CI): falha abaixo do piso do pyproject.toml
	@mkdir -p $(COV_DIR)
	cd backend && MIGRATIONS_DATABASE_URL="$${TEST_MIGRATIONS_DATABASE_URL:-$$MIGRATIONS_DATABASE_URL}" uv run alembic upgrade head
	cd backend && COVERAGE_CORE=sysmon uv run pytest -n $(COVERAGE_WORKERS) --cov=app --cov-report=term --cov-report=json:$(COV_DIR)/backend.json

coverage-frontend: ## Cobertura do frontend (passo de CI): falha abaixo do piso do vite.config.ts
	@mkdir -p $(COV_DIR)
	cd frontend && npm run test:coverage -- --coverage.reporter=text-summary --coverage.reporter=json-summary --coverage.reportsDirectory=$(COV_DIR)/frontend

coverage-summary-backend: ## Publica a cobertura medida do backend no resumo do CI
	python3 scripts/coverage_summary.py backend $(COV_DIR)

coverage-summary-frontend: ## Publica a cobertura medida do frontend no resumo do CI
	python3 scripts/coverage_summary.py frontend $(COV_DIR)

docker-image: ## Constrói a imagem de produção do backend (rito-backend:ci)
	docker build -t rito-backend:ci backend

image-smoke: ## Confere a imagem: não roda como root, sem gcc, `rito health` passa em produção
	@if [ "$$(docker run --rm rito-backend:ci id -u)" = "0" ]; then echo "a imagem roda como root" >&2; exit 1; fi
	@if docker run --rm rito-backend:ci sh -c 'command -v gcc >/dev/null 2>&1'; then echo "gcc sobreviveu na imagem final" >&2; exit 1; fi
	docker run --rm --network host \
		-e APP_ENV=production \
		-e SECRET_KEY="$$(openssl rand -hex 32)" \
		-e DATABASE_URL="$$TEST_DATABASE_URL" \
		-e MIGRATIONS_DATABASE_URL="$$TEST_MIGRATIONS_DATABASE_URL" \
		-e REDIS_URL="$$REDIS_URL" \
		-e S3_ENDPOINT_URL="$$S3_ENDPOINT_URL" -e S3_ACCESS_KEY="$$S3_ACCESS_KEY" \
		-e S3_SECRET_KEY="$$S3_SECRET_KEY" -e S3_BUCKET="$$S3_BUCKET" \
		-e S3_REGION="$$S3_REGION" \
		-e CORS_ALLOWED_ORIGINS="https://app.exemplo.com.br" \
		rito-backend:ci rito health

ci-db: ## (CI) Cria a role de aplicação e o banco rito_test no Postgres do service
	PGPASSWORD=rito psql -h localhost -U rito -d rito -c "CREATE ROLE rito_app LOGIN PASSWORD 'rito_app';"
	PGPASSWORD=rito psql -h localhost -U rito -d rito -c "CREATE DATABASE rito_test OWNER rito;"

# O bloco `services:` do Actions não passa o CMD `server /data` do MinIO (igual ao
# docker-compose.yml), então o container sobe com `docker run` e a espera é por condição.
ci-minio: ## (CI) Sobe o MinIO e espera o health endpoint responder
	docker run -d --name minio -p 9000:9000 \
		-e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin \
		--tmpfs /data cgr.dev/chainguard/minio:latest server /data
	@for _ in $$(seq 1 30); do \
		if curl -sf http://localhost:9000/minio/health/live >/dev/null; then echo "MinIO pronto"; exit 0; fi; \
		sleep 1; \
	done; echo "MinIO não respondeu a tempo" >&2; exit 1

ci-gate: ## (CI) Falha se o run inteiro passou de CI_WALL_CLOCK_BUDGET segundos
	CI_WALL_CLOCK_BUDGET=$(CI_WALL_CLOCK_BUDGET) bash scripts/ci_gate.sh

# Tipos do frontend a partir do contrato da API (frontend-standard). Gerado, não editado.
api-types: openapi ## Gera frontend/generated/api-schema.ts a partir de backend/openapi.json
	cd frontend && npm run types:api

api-types-check: api-types ## Falha se o tipo gerado não bate com o commit (CI)
	git diff --exit-code -- frontend/generated/api-schema.ts

bundle: ## Build de produção e gate do bundle inicial (teto 250 KB gzip)
	cd frontend && npm run bundle
