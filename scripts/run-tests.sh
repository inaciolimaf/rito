#!/usr/bin/env bash
# Roda as 3 suítes (backend, frontend, e2e) concorrentes e falha se o
# wall-clock total passar do orçamento (CLAUDE.md §3). Isso é um gate, não um aviso.
set -uo pipefail

# A lógica fica em main() e só roda quando o arquivo é EXECUTADO, não quando é
# sourced — tests/meta/test_runner.sh soura este arquivo e sobrescreve
# run_backend/run_frontend/run_e2e para simular falha/estouro de orçamento sem
# rodar as suítes de verdade (spec 009, plano de testes).
run_backend() {
	cd backend
	# Migration aplicada uma vez por invocação da suíte, antes dos workers do -n auto
	# subirem — spec 009 regra 3 ("template database criada uma vez por sessão").
	# Tem que migrar o banco de TESTE (rito_test via TEST_MIGRATIONS_DATABASE_URL), não o
	# de dev — tests/conftest.py::pytest_configure só troca MIGRATIONS_DATABASE_URL dentro
	# do processo do pytest; este `alembic upgrade head` roda antes, como subprocesso
	# separado, e herdaria a URL de dev sem este override explícito.
	MIGRATIONS_DATABASE_URL="${TEST_MIGRATIONS_DATABASE_URL:-$MIGRATIONS_DATABASE_URL}" \
		uv run alembic upgrade head
	# Limpa o acúmulo de tenants de runs anteriores (spec 032): make_user COMITA tenant +
	# usuário por teste e nada limpava — em agosto/2026 o rito_test tinha 9.317 tenants e
	# 1,16 milhão de task_types (seed da 031: 152 por tenant), e a suíte inteira pagava
	# IO/vacuum disso. Os testes criam tudo que precisam via fixtures; os catálogos
	# globais (courts, steps, occupations, cidades) ficam — não têm FK para tenants.
	MIGRATIONS_DATABASE_URL="${TEST_MIGRATIONS_DATABASE_URL:-$MIGRATIONS_DATABASE_URL}" \
		uv run python -c "
import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def main() -> None:
    engine = create_async_engine(os.environ['MIGRATIONS_DATABASE_URL'])
    async with engine.begin() as conn:
        await conn.execute(text('TRUNCATE tenants CASCADE'))
    await engine.dispose()


asyncio.run(main())
"
	if [ -n "${PYTEST_ALLOW_HOSTS:-}" ]; then
		uv run pytest -n auto --allow-hosts="$PYTEST_ALLOW_HOSTS"
	else
		uv run pytest -n auto
	fi
}

run_frontend() {
	cd frontend && npm run test
}

run_e2e() {
	if find e2e/tests -type f -name '*.spec.ts' | grep -q .; then
		cd e2e && npm test
	else
		echo "e2e: nenhuma jornada ainda — pulando"
	fi
}

main() {
	cd "$(dirname "${BASH_SOURCE[0]}")/.."

	local budget_seconds="${TEST_WALL_CLOCK_BUDGET_SECONDS:-120}"
	local start_time
	start_time=$(date +%s)

	local pids=()
	local logs_dir
	logs_dir="$(mktemp -d)"

	run_backend >"$logs_dir/backend.log" 2>&1 &
	pids+=("$!:backend")
	run_frontend >"$logs_dir/frontend.log" 2>&1 &
	pids+=("$!:frontend")
	run_e2e >"$logs_dir/e2e.log" 2>&1 &
	pids+=("$!:e2e")

	local overall_status=0
	for entry in "${pids[@]}"; do
		local pid="${entry%%:*}"
		local name="${entry##*:}"
		if ! wait "$pid"; then
			echo "--- $name FALHOU ---"
			cat "$logs_dir/$name.log"
			overall_status=1
		else
			echo "--- $name ok ---"
			cat "$logs_dir/$name.log"
		fi
	done

	local end_time elapsed
	end_time=$(date +%s)
	elapsed=$((end_time - start_time))
	echo "wall-clock: ${elapsed}s (orçamento: ${budget_seconds}s)"

	if [ "$elapsed" -gt "$budget_seconds" ]; then
		echo "FALHA: wall-clock de ${elapsed}s excedeu o orçamento de ${budget_seconds}s"
		overall_status=1
	fi

	# Regra 7: test-timing.json versiona o wall-clock a cada spec. Atualiza só o resumo
	# (last_measured_*) automaticamente — o detalhamento por spec em "specs" continua manual,
	# preenchido no ciclo do /loop com o que mudou.
	if [ "$overall_status" -eq 0 ] && command -v python3 >/dev/null; then
		python3 - "$elapsed" <<'EOF'
import json
import sys
from datetime import datetime, timezone

elapsed = int(sys.argv[1])
path = "test-timing.json"
with open(path) as f:
    data = json.load(f)
data["last_measured_wall_clock_seconds"] = elapsed
data["last_measured_at"] = datetime.now(timezone.utc).date().isoformat()
with open(path, "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")
EOF
	fi

	rm -rf "$logs_dir"
	return "$overall_status"
}

# Só executa main automaticamente quando o script roda diretamente. Quando sourced
# (tests/meta/test_runner.sh), quem chama main() é o teste, depois de sobrescrever
# run_backend/run_frontend/run_e2e.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
	main
	exit $?
fi
