#!/usr/bin/env bash
# Regras 1-2 da spec 009: run-tests.sh falha se uma suíte falha, e falha se o
# wall-clock passar do orçamento — mesmo com as três suítes verdes.
#
# Soura scripts/run-tests.sh (a lógica fica em main(), guardada por
# BASH_SOURCE == 0 — sourced não auto-executa) e sobrescreve run_backend/
# run_frontend/run_e2e para simular os dois cenários sem rodar as suítes de
# verdade — este teste roda em milissegundos, não minutos.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
failures=0

# Cenário C (abaixo) passa com tudo verde, então main() vai reescrever
# test-timing.json de verdade (regra 7) — backup/restore para não deixar o
# repositório sujo com um wall-clock de teste sintético.
cp "$REPO_ROOT/test-timing.json" "$REPO_ROOT/test-timing.json.bak"
trap 'mv "$REPO_ROOT/test-timing.json.bak" "$REPO_ROOT/test-timing.json"' EXIT

check() {
	local description="$1"
	local expected_status="$2"
	local actual_status="$3"
	if [ "$actual_status" -eq "$expected_status" ]; then
		echo "ok - $description"
	else
		echo "FALHOU - $description (esperado status $expected_status, veio $actual_status)"
		failures=$((failures + 1))
	fi
}

# Cenário A: uma suíte falha -> main() tem que sair != 0, mesmo com as outras duas ok.
(
	source "$REPO_ROOT/scripts/run-tests.sh"
	run_backend() { return 1; }
	run_frontend() { return 0; }
	run_e2e() { return 0; }
	main >/dev/null 2>&1
)
check "suíte falhando derruba o gate" 1 "$?"

# Cenário B: as três suítes passam instantaneamente, mas o orçamento é 0s -> o
# wall-clock medido (>= 0s, e o loop/soma leva > 0s de verdade) estoura e o gate falha.
(
	source "$REPO_ROOT/scripts/run-tests.sh"
	run_backend() { return 0; }
	run_frontend() { return 0; }
	run_e2e() { return 0; }
	export TEST_WALL_CLOCK_BUDGET_SECONDS=-1
	main >/dev/null 2>&1
)
check "wall-clock acima do orçamento derruba o gate mesmo com tudo verde" 1 "$?"

# Cenário C: controle — as três passam e o orçamento é folgado -> gate tem que passar.
(
	source "$REPO_ROOT/scripts/run-tests.sh"
	run_backend() { return 0; }
	run_frontend() { return 0; }
	run_e2e() { return 0; }
	export TEST_WALL_CLOCK_BUDGET_SECONDS=120
	main >/dev/null 2>&1
)
check "tudo verde e dentro do orçamento passa o gate" 0 "$?"

if [ "$failures" -gt 0 ]; then
	echo "$failures cenário(s) falharam"
	exit 1
fi
echo "todos os cenários do gate de run-tests.sh passaram"
