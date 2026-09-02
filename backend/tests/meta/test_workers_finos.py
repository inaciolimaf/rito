"""Spec 117, regras 4 e 5: a exclusão de `app/workers/*` da cobertura só é honesta
enquanto os corpos de task continuarem finos.

`app/workers/*` sai da medição porque nenhum teste importa worker — chamar uma varredura
por tenant abre um engine por tenant e leva minutos. A decisão é defensável, mas sem gate
ela é indistinguível de negligência: `workers/` viraria o esconderijo natural de código
que alguém não quis testar. Estes dois testes são a outra metade da decisão.

O que "fino" quer dizer aqui: a função monta a infra de produção (engine, redis, http
client, session factory), agrupa e despacha. A regra de negócio mora no service, que os
testes exercitam direto. Uma task que cresce está trazendo regra para dentro de um lugar
que a cobertura não mede.
"""

import ast
import tomllib
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
WORKERS_DIR = BACKEND_DIR / "app" / "workers"
PYPROJECT = BACKEND_DIR / "pyproject.toml"

# Teto da regra 5 da spec 117 para função NOVA de worker.
MAX_STATEMENTS = 15

# Medido em 01/09/2026 (spec 117). A regra 5 pede 15; cinco funções de montagem de infra
# já nasceram acima disso, e todas as cinco são wiring + despacho — nenhuma carrega regra
# de negócio (a de `djen_sync.run_due_syncs`, a maior, mora em `TermSyncService`).
#
# Baixar as cinco para 15 é refatoração de comportamento em `app/workers/`, que a 117
# declara fora de escopo ("nenhuma mudança de comportamento; só medição, configuração e
# as exclusões justificadas"). Então elas entram aqui com o número EXATO medido: não é
# silenciar, é catraca. Nenhuma função nova pode nascer acima de 15, e nenhuma destas
# cinco pode crescer um único statement sem que este teste caia.
#
# Toda linha que sair desta tabela (porque a função encolheu ou sumiu) é ganho
# permanente — o teste também falha se uma entrada ficar sobrando.
BASELINE: dict[str, int] = {
    "djen_sync.py::run_due_syncs": 26,
    # Spec 114: caiu de 29 para 21 ao extrair `_check_tenant` — o corpo do laço cresceu
    # quando o fuso passou a ser resolvido por tenant, e a catraca só desce.
    "integration_health.py::run_daily_check": 20,
    "datajud_sync.py::run_scheduled_sync": 26,
    "aggregates.py::refresh_aggregate": 19,
    "aggregates.py::refresh_due_aggregates": 19,
}


def _statements(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Statements executáveis do corpo, docstring de fora — a mesma unidade que a
    cobertura conta, medida por AST porque a cobertura não quebra por função."""
    total = 0
    for child in ast.walk(node):
        if child is node or not isinstance(child, ast.stmt):
            continue
        if _e_docstring(child, node):
            continue
        total += 1
    return total


def _e_docstring(stmt: ast.stmt, root: ast.AST) -> bool:
    for holder in ast.walk(root):
        if not isinstance(holder, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        primeiro = holder.body[0] if holder.body else None
        if (
            primeiro is stmt
            and isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        ):
            return True
    return False


def _funcoes_de_worker() -> dict[str, int]:
    medidas: dict[str, int] = {}
    for path in sorted(WORKERS_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                medidas[f"{path.name}::{node.name}"] = _statements(node)
    return medidas


def test_corpo_de_task_continua_fino() -> None:
    medidas = _funcoes_de_worker()

    acima_do_teto = {
        nome: total
        for nome, total in medidas.items()
        if total > MAX_STATEMENTS and nome not in BASELINE
    }
    assert acima_do_teto == {}, (
        f"função de app/workers/ acima de {MAX_STATEMENTS} statements: "
        + ", ".join(f"{nome} ({total})" for nome, total in sorted(acima_do_teto.items()))
        + ". A regra de negócio vazou para o worker, e `app/workers/*` está FORA da "
        "medição de cobertura (spec 117, regras 4 e 5) — o que entra aqui não é testado "
        "por ninguém. Mova a regra para o service."
    )

    cresceram = {
        nome: (medidas[nome], teto)
        for nome, teto in BASELINE.items()
        if nome in medidas and medidas[nome] > teto
    }
    assert cresceram == {}, (
        "função já grande de app/workers/ cresceu: "
        + ", ".join(
            f"{nome} {agora} statements (baseline {teto})"
            for nome, (agora, teto) in sorted(cresceram.items())
        )
        + ". A catraca da spec 117 só desce."
    )

    encolheram = {
        nome: (medidas.get(nome), teto)
        for nome, teto in BASELINE.items()
        if nome not in medidas or medidas[nome] < teto
    }
    assert encolheram == {}, (
        "o BASELINE deste arquivo está desatualizado (a função encolheu ou sumiu — bom "
        "sinal). Atualize a entrada para o número medido, ou remova-a se já couber em "
        f"{MAX_STATEMENTS}: "
        + ", ".join(
            f"{nome} agora {agora} (baseline {teto})"
            for nome, (agora, teto) in sorted(encolheram.items())
        )
    )


def test_exclusao_de_cobertura_e_justificada() -> None:
    """Regra 4: `app/workers/*` fora da medição **com** justificativa no pyproject.toml
    citando a spec. Exclusão sem justificativa escrita é buraco disfarçado de decisão."""
    texto = PYPROJECT.read_text(encoding="utf-8")
    config = tomllib.loads(texto)

    omitidos = config.get("tool", {}).get("coverage", {}).get("run", {}).get("omit", [])
    assert omitidos, (
        "spec 117: `app/workers/*` precisa estar em [tool.coverage.run] omit do "
        "pyproject.toml — o piso de cobertura vale sobre o recorte sem workers."
    )

    # O bloco [tool.coverage.run] precisa de comentário citando a spec: é a justificativa
    # que a regra 4 exige e o que a 120 vai conferir.
    bloco = texto.split("[tool.coverage.run]", 1)[1].split("\n[", 1)[0]
    assert "117" in bloco, (
        "a exclusão de cobertura em [tool.coverage.run] não cita a spec que a autoriza. "
        "Spec 117, regra 4: a exclusão e a justificativa escrita são as duas metades da "
        "mesma decisão."
    )

    fora_do_combinado = [padrao for padrao in omitidos if not padrao.startswith("app/workers")]
    assert fora_do_combinado == [], (
        "módulo excluído da cobertura além de app/workers/: "
        + ", ".join(fora_do_combinado)
        + ". A spec 117 autoriza UMA exclusão. Qualquer outra precisa de spec própria — "
        "senão o piso mede o que sobrou, não o que existe."
    )
