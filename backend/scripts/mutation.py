"""Mutador mínimo por AST (spec 132) — mede se a suíte MATA o defeito, não se ela executa a linha.

Cobertura é proxy: uma linha executada por um teste que não olha o resultado conta como
coberta. Teste de mutação é a medição direta — estraga o código de propósito e pergunta se
alguma asserção reclama. Um mutante que **sobrevive** é uma afirmação que ninguém verifica.

Por que um mutador próprio e não o `mutmut`/`cosmic-ray`: as duas ferramentas são boas e
foram avaliadas (§9 da spec 132). O `mutmut` 3.7 exige `source_paths` num `setup.cfg` na
raiz do backend e materializa uma cópia da árvore em `mutants/` — configuração e diretório
novos no repositório para um experimento de três arquivos. Aqui o experimento é pequeno de
propósito, e este arquivo cabe numa leitura.

Como funciona:

1. lê o módulo, faz o parse e enumera os nós por ordem estável de `ast.walk`;
2. para cada nó aplicável gera um mutante (uma cópia profunda da árvore com UMA alteração);
3. descarta mutante cujo código gerado é idêntico ao original (equivalente por construção);
4. roda o **controle de identidade** — a árvore reescrita SEM mutação tem de passar, senão
   o `ast.unparse` está mudando comportamento e a medição toda é lixo;
5. roda a suíte rápida para cada mutante; o que sobreviver é reconferido contra a suíte
   completa (`--confirm-tests`), porque sobrevivente é o produto e não pode ser artefato de
   ter rodado poucos testes.

O processo filho vem de `os.fork` + `pytest.main`, não de `subprocess`: economiza o
arranque do interpretador em cada mutante (~0,9 s de 1,4 s) e não precisa de `# noqa: S603`
— o teto de silenciamento de `S*` do projeto está cheio (`docs/GATES.md` §1).

**Isto NUNCA entra no `make test`** (CLAUDE.md §3): o orçamento é de 300 s de wall-clock
para as três suítes, e uma rodada de mutação de um módulo custa minutos. É ferramenta de
medição pontual, no molde do `make test-nightly`.

Uso (o alvo é reescrito no lugar; aponte para uma CÓPIA da árvore, nunca para o repositório):

    python -m scripts.mutation --root /caminho/da/copia \\
        --module app/domain/ai/sql_guard.py \\
        --tests tests/unit/test_sql_guard.py \\
        --confirm-tests tests/unit/test_sql_guard.py tests/integration/test_ai_security.py \\
        --json relatorio.json
"""

from __future__ import annotations

import argparse
import ast
import copy
import json
import os
import signal
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

Applier = Callable[[ast.AST], None]
_ConstantValue = str | int | bool

_POLL_SECONDS = 0.02
_TIMEOUT_EXIT = -99
_MUTATED_TEXT = "rito-mutante"

# --------------------------------------------------------------------------------------
# As tabelas de mutação. Clássicas de propósito: cada uma corresponde a um erro que um
# humano comete de verdade — a borda trocada, o conectivo trocado, o sinal trocado, a
# constante vizinha, a negação perdida, a chamada esquecida.
# --------------------------------------------------------------------------------------

_COMPARE_SWAPS: dict[type[ast.cmpop], type[ast.cmpop]] = {
    ast.Lt: ast.LtE,
    ast.LtE: ast.Lt,
    ast.Gt: ast.GtE,
    ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
}

_BINOP_SWAPS: dict[type[ast.operator], type[ast.operator]] = {
    ast.Add: ast.Sub,
    ast.Sub: ast.Add,
    ast.Mult: ast.FloorDiv,
    ast.Div: ast.Mult,
    ast.FloorDiv: ast.Mult,
    ast.Mod: ast.FloorDiv,
}

_BOOLOP_SWAPS: dict[type[ast.boolop], type[ast.boolop]] = {ast.And: ast.Or, ast.Or: ast.And}

_OP_TEXT: dict[type[ast.AST], str] = {
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.Is: "is",
    ast.IsNot: "is not",
    ast.In: "in",
    ast.NotIn: "not in",
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.FloorDiv: "//",
    ast.Mod: "%",
    ast.And: "and",
    ast.Or: "or",
}


@dataclass(frozen=True)
class Plan:
    """Uma mutação: onde, de que família, o que muda e como aplicar."""

    index: int
    line: int
    kind: str
    label: str
    apply: Applier


@dataclass(frozen=True)
class Mutant:
    """Um mutante já materializado — o plano mais o código-fonte que ele gera."""

    module: str
    line: int
    kind: str
    label: str
    source: str


# --------------------------------------------------------------------------------------
# Geração
# --------------------------------------------------------------------------------------


def _swap_in_list(items: list[Any], old: ast.AST, new: ast.AST) -> bool:
    for position, item in enumerate(items):
        if item is old:
            items[position] = new
            return True
    return False


def _replace_child(tree: ast.AST, old: ast.AST, new: ast.AST) -> None:
    """Troca `old` por `new` no primeiro pai que o contiver."""
    for parent in ast.walk(tree):
        for field, value in ast.iter_fields(parent):
            if value is old:
                setattr(parent, field, new)
                return
            if isinstance(value, list) and _swap_in_list(value, old, new):
                return


def _compare_plans(index: int, node: ast.Compare) -> Iterator[Plan]:
    for slot, operador in enumerate(node.ops):
        novo = _COMPARE_SWAPS.get(type(operador))
        if novo is None:
            continue

        def _apply(alvo: ast.AST, slot: int = slot, novo: type[ast.cmpop] = novo) -> None:
            cast(ast.Compare, alvo).ops[slot] = novo()

        rotulo = f"{_OP_TEXT[type(operador)]} → {_OP_TEXT[novo]}"
        yield Plan(index, node.lineno, "comparador", rotulo, _apply)


def _boolop_plans(index: int, node: ast.BoolOp) -> Iterator[Plan]:
    novo = _BOOLOP_SWAPS[type(node.op)]

    def _apply(alvo: ast.AST) -> None:
        cast(ast.BoolOp, alvo).op = novo()

    yield Plan(
        index, node.lineno, "conectivo", f"{_OP_TEXT[type(node.op)]} → {_OP_TEXT[novo]}", _apply
    )


def _binop_plans(index: int, node: ast.BinOp) -> Iterator[Plan]:
    novo = _BINOP_SWAPS.get(type(node.op))
    if novo is None:
        return

    def _apply(alvo: ast.AST) -> None:
        cast(ast.BinOp, alvo).op = novo()

    yield Plan(
        index, node.lineno, "aritmética", f"{_OP_TEXT[type(node.op)]} → {_OP_TEXT[novo]}", _apply
    )


def _constant_values(valor: object) -> Iterator[tuple[str, _ConstantValue]]:
    """As trocas de constante: booleano invertido, inteiro vizinho, texto trocado."""
    if isinstance(valor, bool):
        yield f"{valor} → {not valor}", not valor
    elif isinstance(valor, int):
        yield f"{valor} → {valor + 1}", valor + 1
        yield f"{valor} → {valor - 1}", valor - 1
    elif isinstance(valor, str):
        yield (f"{valor!r} → ''", "") if valor else ("'' → texto", _MUTATED_TEXT)


def _constant_plans(index: int, node: ast.Constant) -> Iterator[Plan]:
    for rotulo, valor in _constant_values(node.value):

        def _apply(alvo: ast.AST, valor: _ConstantValue = valor) -> None:
            cast(ast.Constant, alvo).value = valor

        yield Plan(index, node.lineno, "constante", rotulo, _apply)


def _unary_plans(index: int, node: ast.UnaryOp) -> Iterator[Plan]:
    if not isinstance(node.op, ast.Not):
        return

    def _apply(alvo: ast.AST) -> None:
        raise _ReplaceNode(cast(ast.UnaryOp, alvo).operand)

    yield Plan(index, node.lineno, "negação", "`not X` → `X`", _apply)


def _expr_plans(index: int, node: ast.Expr) -> Iterator[Plan]:
    """Chamada solta como statement (log, `super().__init__`) vira `None` — some do fluxo."""
    if not isinstance(node.value, ast.Call):
        return

    def _apply(alvo: ast.AST) -> None:
        cast(ast.Expr, alvo).value = ast.Constant(value=None)

    yield Plan(index, node.lineno, "chamada removida", _call_name(node.value), _apply)


def _call_name(call: ast.Call) -> str:
    alvo = call.func
    if isinstance(alvo, ast.Attribute):
        return f"remove `…{alvo.attr}(…)`"
    if isinstance(alvo, ast.Name):
        return f"remove `{alvo.id}(…)`"
    return "remove chamada"


class _ReplaceNode(Exception):
    """Sinaliza que a mutação troca o próprio nó, e não um atributo dele."""

    def __init__(self, novo: ast.AST) -> None:
        super().__init__("substituição de nó")
        self.novo = novo


_GENERATORS: dict[type[ast.AST], Callable[[int, Any], Iterator[Plan]]] = {
    ast.Compare: _compare_plans,
    ast.BoolOp: _boolop_plans,
    ast.BinOp: _binop_plans,
    ast.Constant: _constant_plans,
    ast.UnaryOp: _unary_plans,
    ast.Expr: _expr_plans,
}


def _docstring_ids(tree: ast.Module) -> set[int]:
    """Docstrings ficam de fora: mutá-las gera equivalente puro e infla o denominador."""
    encontrados: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        corpo = node.body
        if corpo and isinstance(corpo[0], ast.Expr) and isinstance(corpo[0].value, ast.Constant):
            encontrados.add(id(corpo[0]))
            encontrados.add(id(corpo[0].value))
    return encontrados


def _plans(tree: ast.Module) -> list[Plan]:
    ignorados = _docstring_ids(tree)
    planos: list[Plan] = []
    for index, node in enumerate(ast.walk(tree)):
        gerador = _GENERATORS.get(type(node))
        if gerador is None or id(node) in ignorados:
            continue
        planos.extend(gerador(index, node))
    return planos


def _materialize(tree: ast.Module, plano: Plan, module: str) -> Mutant | None:
    """Aplica UM plano numa cópia profunda e devolve o código gerado."""
    copia = copy.deepcopy(tree)
    alvo = list(ast.walk(copia))[plano.index]
    try:
        plano.apply(alvo)
    except _ReplaceNode as troca:
        _replace_child(copia, alvo, troca.novo)
    ast.fix_missing_locations(copia)
    codigo = ast.unparse(copia)
    if codigo == ast.unparse(tree):
        return None
    return Mutant(module, plano.line, plano.kind, plano.label, codigo)


def build_mutants(path: Path, module: str) -> tuple[str, list[Mutant]]:
    """Devolve o código de CONTROLE (reescrito, sem mutação) e a lista de mutantes."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    controle = ast.unparse(tree)
    mutantes = [m for plano in _plans(tree) if (m := _materialize(tree, plano, module))]
    return controle, mutantes


# --------------------------------------------------------------------------------------
# Execução
# --------------------------------------------------------------------------------------


def _child(root: Path, argumentos: list[str], log: Path) -> None:
    """Roda a suíte e encerra o processo — nunca retorna."""
    os.chdir(root)
    saida = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.dup2(saida, 1)
    os.dup2(saida, 2)
    import pytest

    codigo = pytest.main(["-x", "-q", "-p", "no:cacheprovider", *argumentos])
    os._exit(int(codigo))


def _wait(pid: int, timeout: float) -> int:
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        terminado, status = os.waitpid(pid, os.WNOHANG)
        if terminado == pid:
            return os.waitstatus_to_exitcode(status)
        time.sleep(_POLL_SECONDS)
    os.kill(pid, signal.SIGKILL)
    os.waitpid(pid, 0)
    return _TIMEOUT_EXIT


def run_suite(root: Path, argumentos: list[str], log: Path, timeout: float) -> int:
    """0 = suíte verde. Qualquer outra coisa = suíte vermelha (mutante morto)."""
    pid = os.fork()
    if pid == 0:  # pragma: no cover - o filho nunca volta
        _child(root, argumentos, log)
    return _wait(pid, timeout)


def _survives(
    root: Path, path: Path, mutant: Mutant, opcoes: argparse.Namespace, log: Path
) -> bool:
    path.write_text(mutant.source, encoding="utf-8")
    if run_suite(root, opcoes.tests, log, opcoes.timeout) != 0:
        return False
    if not opcoes.confirm_tests:
        return True
    return run_suite(root, opcoes.confirm_tests, log, opcoes.timeout) == 0


def _check_control(
    root: Path, path: Path, controle: str, opcoes: argparse.Namespace, log: Path
) -> None:
    """Sem este controle a medição não vale: prova que reescrever a árvore não muda nada."""
    path.write_text(controle, encoding="utf-8")
    codigo = run_suite(root, opcoes.tests, log, opcoes.timeout)
    if codigo != 0:
        sys.stdout.write(log.read_text(encoding="utf-8"))
        raise SystemExit(
            f"controle de identidade reprovou ({codigo}) — `ast.unparse` mudou o módulo"
        )


def _report(module: str, mutantes: list[Mutant], sobreviventes: list[Mutant]) -> dict[str, Any]:
    mortos = len(mutantes) - len(sobreviventes)
    return {
        "module": module,
        "measured_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "mutants": len(mutantes),
        "killed": mortos,
        "survived": len(sobreviventes),
        "score_percent": round(100.0 * mortos / len(mutantes), 1) if mutantes else 100.0,
        "survivors": [{"line": m.line, "kind": m.kind, "mutation": m.label} for m in sobreviventes],
    }


def run_module(root: Path, relativo: str, opcoes: argparse.Namespace) -> dict[str, Any]:
    path = root / relativo
    original = path.read_text(encoding="utf-8")
    log = Path(opcoes.log)
    controle, mutantes = build_mutants(path, relativo)
    sobreviventes: list[Mutant] = []
    try:
        _check_control(root, path, controle, opcoes, log)
        for posicao, mutante in enumerate(mutantes, start=1):
            vivo = _survives(root, path, mutante, opcoes, log)
            if vivo:
                sobreviventes.append(mutante)
            marca = "VIVO " if vivo else "morto"
            print(f"  [{posicao:>3}/{len(mutantes)}] {marca} L{mutante.line:<4} {mutante.label}")
    finally:
        path.write_text(original, encoding="utf-8")
    return _report(relativo, mutantes, sobreviventes)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Teste de mutação mínimo (spec 132).")
    parser.add_argument("--root", required=True, help="raiz da CÓPIA da árvore a mutar")
    parser.add_argument("--module", action="append", required=True, help="caminho relativo à raiz")
    parser.add_argument("--tests", nargs="+", required=True, help="suíte rápida, por mutante")
    parser.add_argument("--confirm-tests", nargs="*", default=[], help="suíte de reconferência")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--log", default=str(Path(tempfile.gettempdir()) / "rito-mutation.log"))
    parser.add_argument("--json", dest="json_path", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    opcoes = _parse_args(argv)
    root = Path(opcoes.root).resolve()
    relatorios = []
    for relativo in opcoes.module:
        print(f"\n== {relativo}")
        relatorio = run_module(root, relativo, opcoes)
        print(
            f"   {relatorio['killed']}/{relatorio['mutants']} mortos "
            f"({relatorio['score_percent']}%), {relatorio['survived']} vivos"
        )
        relatorios.append(relatorio)
    if opcoes.json_path:
        Path(opcoes.json_path).write_text(
            json.dumps(relatorios, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
