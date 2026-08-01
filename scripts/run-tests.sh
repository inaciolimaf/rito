#!/usr/bin/env bash
# Roda as 3 suítes (backend, frontend, e2e) concorrentes e falha se o
# wall-clock total passar do orçamento (CLAUDE.md §3). Isso é um gate, não um aviso.
set -uo pipefail

cd "$(dirname "$0")/.."

BUDGET_SECONDS="${TEST_WALL_CLOCK_BUDGET_SECONDS:-120}"
start_time=$(date +%s)

pids=()
logs_dir="$(mktemp -d)"

run_backend() {
	cd backend && uv run pytest -n auto
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

run_backend >"$logs_dir/backend.log" 2>&1 &
pids+=("$!:backend")
run_frontend >"$logs_dir/frontend.log" 2>&1 &
pids+=("$!:frontend")
run_e2e >"$logs_dir/e2e.log" 2>&1 &
pids+=("$!:e2e")

overall_status=0
for entry in "${pids[@]}"; do
	pid="${entry%%:*}"
	name="${entry##*:}"
	if ! wait "$pid"; then
		echo "--- $name FALHOU ---"
		cat "$logs_dir/$name.log"
		overall_status=1
	else
		echo "--- $name ok ---"
		cat "$logs_dir/$name.log"
	fi
done

end_time=$(date +%s)
elapsed=$((end_time - start_time))
echo "wall-clock: ${elapsed}s (orçamento: ${BUDGET_SECONDS}s)"

if [ "$elapsed" -gt "$BUDGET_SECONDS" ]; then
	echo "FALHA: wall-clock de ${elapsed}s excedeu o orçamento de ${BUDGET_SECONDS}s"
	overall_status=1
fi

rm -rf "$logs_dir"
exit "$overall_status"
