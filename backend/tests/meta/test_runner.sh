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

# ---------------------------------------------------------------------------
# Spec 139 — os cenários do `run_e2e`, que o teste não cobria.
#
# Os três acima sobrescrevem run_e2e e nunca o executam; o `else` do original —
# "e2e: nenhuma jornada ainda — pulando", com exit 0 — era o quarto caminho por
# onde a suíte de e2e inteira sumia sem vermelho. É a mesma assinatura do achado
# da spec 131: um gate que via três de quatro casos.
#
# Os dois cenários rodam num diretório temporário porque `run_e2e` procura em
# `e2e/tests` relativo ao diretório corrente.
# ---------------------------------------------------------------------------

sandbox="$(mktemp -d)"
trap 'mv "$REPO_ROOT/test-timing.json.bak" "$REPO_ROOT/test-timing.json"; rm -rf "$sandbox"' EXIT
mkdir -p "$sandbox/e2e/tests/meta"

# Cenário D: e2e/tests sem nenhuma jornada (só o gate de contagem) -> tem que FALHAR.
(
	source "$REPO_ROOT/scripts/run-tests.sh"
	_e2e_runner() { return 0; }
	echo 'test("conta", () => {});' >"$sandbox/e2e/tests/meta/journey-count.spec.ts"
	cd "$sandbox" && run_e2e >/dev/null 2>&1
)
check "e2e sem nenhuma jornada derruba o gate (não 'pulando')" 1 "$?"

# Cenário E: diretório inexistente -> mesma falha, sem ruído de `find` no stderr.
(
	source "$REPO_ROOT/scripts/run-tests.sh"
	_e2e_runner() { return 0; }
	cd "$(mktemp -d)" && run_e2e >/dev/null 2>&1
)
check "e2e/tests inexistente derruba o gate" 1 "$?"

# Cenário F: controle — com jornada, run_e2e chega no runner e devolve o que ele devolve.
(
	source "$REPO_ROOT/scripts/run-tests.sh"
	_e2e_runner() { return 0; }
	echo 'test("jornada", async ({ page }) => {});' >"$sandbox/e2e/tests/auth.spec.ts"
	cd "$sandbox" && run_e2e >/dev/null 2>&1
)
check "com jornada, run_e2e delega ao runner (controle)" 0 "$?"

# Cenário G: e o controle não vira falso negativo — runner vermelho continua vermelho.
(
	source "$REPO_ROOT/scripts/run-tests.sh"
	_e2e_runner() { return 1; }
	cd "$sandbox" && run_e2e >/dev/null 2>&1
)
check "runner de e2e falhando derruba o gate" 1 "$?"

if [ "$failures" -gt 0 ]; then
	echo "$failures cenário(s) falharam"
	exit 1
fi
echo "todos os cenários do gate de run-tests.sh passaram"
