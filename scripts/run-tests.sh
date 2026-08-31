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
	# Numa máquina limpa (Docker nativo, shell sem TEST_* exportado) o `set -u` do topo
	# derrubava a suíte inteira com "unbound variable" antes de rodar um único teste: o
	# `.env` da raiz é lido pelo pydantic-settings dentro do processo, nunca pelo shell.
	# O default é o MESMO de tests/conftest.py::pytest_configure — banco de TESTE em
	# localhost, nunca o de dev. Quem exporta TEST_MIGRATIONS_DATABASE_URL (CI, host
	# remoto) continua mandando.
	local migrations_url="${TEST_MIGRATIONS_DATABASE_URL:-${MIGRATIONS_DATABASE_URL:-postgresql+asyncpg://rito:rito@localhost:5432/rito_test}}"
	# Migration aplicada uma vez por invocação da suíte, antes dos workers do -n auto
	# subirem — spec 009 regra 3 ("template database criada uma vez por sessão").
	# Tem que migrar o banco de TESTE (rito_test via TEST_MIGRATIONS_DATABASE_URL), não o
	# de dev — tests/conftest.py::pytest_configure só troca MIGRATIONS_DATABASE_URL dentro
	# do processo do pytest; este `alembic upgrade head` roda antes, como subprocesso
	# separado, e herdaria a URL de dev sem este override explícito.
	MIGRATIONS_DATABASE_URL="$migrations_url" \
		uv run alembic upgrade head
	# Spec 105: aqui havia 60 linhas de Python embutido que davam `TRUNCATE tenants
	# CASCADE` uma vez por execução e, antes disso, salvavam e repunham à mão os catálogos
	# globais que o CASCADE levaria junto (o `information_schema` descobria quais eram).
	# Existiam porque cada teste comitava: em agosto/2026 o `rito_test` tinha 9.317 tenants
	# e 1,16 milhão de `task_types`, e a suíte inteira pagava o IO disso.
	#
	# Agora o `rito_test` é o TEMPLATE: nenhum teste escreve nele. Cada worker roda contra
	# uma cópia própria (`rito_test_gwN`), criada por `CREATE DATABASE ... TEMPLATE` no
	# `pytest_configure` e descartada na execução seguinte, e cada teste roda numa
	# transação que sofre ROLLBACK. Não há mais acúmulo para limpar — e limpeza que existe
	# sem ter o que limpar é a próxima a esconder um bug.
	# As 3 suítes rodam CONCORRENTES (CLAUDE.md §3): pytest -n auto (todos os cores) +
	# vitest threads + playwright/uvicorn/vite disputavam 4 cores e o wall-clock
	# oscilava 114→135 s em agosto/2026 (spec 035). Cap em 2 workers por padrão dá ar
	# às outras suítes; PYTEST_WORKERS=auto devolve o comportamento antigo em máquina
	# dedicada (CI com mais cores).
	#
	# Spec 097: o cap subiu de 2 para 3. Quando ele foi escolhido (035) o backend levava
	# ~85 s e as três suítes eram comparáveis; hoje o backend é o poste mais alto por
	# larga margem (~300 s contra ~60 s do frontend e ~80 s do e2e), e as duas outras
	# devolvem seus núcleos nos primeiros 90 s. Segurar o backend em 2 workers pelos
	# 3,5 minutos seguintes deixa metade da máquina ociosa. Medido em host de 4 núcleos:
	# 293 s com 2 workers, 287 s com 3 — e o backend sozinho cai de 300 s para 253 s.
	workers="${PYTEST_WORKERS:-3}"
	if [ -n "${PYTEST_ALLOW_HOSTS:-}" ]; then
		uv run pytest -n "$workers" --allow-hosts="$PYTEST_ALLOW_HOSTS"
	else
		uv run pytest -n "$workers"
	fi
}

run_frontend() {
	# Mesma lógica do cap do backend acima. Medido na spec 036 neste host (4 cores):
	# com 2 threads o vitest disputava CPU com o pytest e o wall-clock ia a 130-147 s;
	# com 1 thread o backend cai para ~85 s e o wall-clock para ~105 s (o vitest, mais
	# barato em valor absoluto, é quem absorve a fila). VITEST_MAX_WORKERS=... sobrescreve.
	cd frontend && npm run test -- --maxWorkers="${VITEST_MAX_WORKERS:-1}"
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

	local budget_seconds="${TEST_WALL_CLOCK_BUDGET_SECONDS:-300}"
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
