"""Cinco bibliotecas pesadas fora do caminho de import (spec 104).

`xhtml2pdf`, `fpdf`, `openpyxl`, `boto3`, `num2words` e `sqlglot` são carregadas dentro
da função que as usa, nunca no topo do módulo. Juntas custavam **438 ms** dos 1,79 s de
`import app.main` — e todo worker do `-n 3` pagava isso antes do primeiro assert, mesmo
sem gerar um PDF sequer.

O teste verifica **estrutura, não tempo**: parseia o AST e falha se um dos nomes voltar
para o topo. Tempo de import medido em CI compartilhado oscila e viraria teste instável —
mesmo raciocínio que a 098 usou para tirar o perfilamento de volume do PR (CLAUDE.md §11).

Import sob `if TYPE_CHECKING:` continua permitido: ele não roda, e é o que mantém
`exp.Expression` resolvível como anotação em `sql_guard.py`.
"""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"

# Módulo → biblioteca que ele carrega sob demanda. A tabela é o contrato da spec 104:
# tirar uma linha daqui é decidir que a biblioteca pode voltar para o topo. O
# `core/export.py` aparece duas vezes porque carrega uma biblioteca por função de export.
CASOS: list[tuple[str, str]] = [
    ("domain/templates/pdf.py", "xhtml2pdf"),
    ("core/export.py", "fpdf"),
    ("core/export.py", "openpyxl"),
    ("integrations/storage/s3.py", "boto3"),
    ("domain/templates/variables.py", "num2words"),
    ("domain/ai/sql_guard.py", "sqlglot"),
]


def _raiz(node: ast.Import | ast.ImportFrom) -> set[str]:
    """O pacote de topo de cada nome importado — `from sqlglot import exp` → `sqlglot`."""
    if isinstance(node, ast.ImportFrom):
        return {(node.module or "").split(".")[0]}
    return {alias.name.split(".")[0] for alias in node.names}


def _e_type_checking(node: ast.stmt) -> bool:
    """`if TYPE_CHECKING:` — o único bloco de topo cujo import não custa nada."""
    if not isinstance(node, ast.If):
        return False
    teste = node.test
    if isinstance(teste, ast.Name):
        return teste.id == "TYPE_CHECKING"
    return isinstance(teste, ast.Attribute) and teste.attr == "TYPE_CHECKING"


def _imports_de_topo(corpo: list[ast.stmt]) -> list[ast.Import | ast.ImportFrom]:
    """Imports que rodam quando o módulo é importado — desce por classes e por `if`,
    que também rodam, e para em função, que não roda."""
    achados: list[ast.Import | ast.ImportFrom] = []
    for node in corpo:
        if isinstance(node, ast.Import | ast.ImportFrom):
            achados.append(node)
        elif isinstance(node, ast.ClassDef):
            achados.extend(_imports_de_topo(node.body))
        elif isinstance(node, ast.If) and not _e_type_checking(node):
            achados.extend(_imports_de_topo([*node.body, *node.orelse]))
    return achados


def _imports_em_funcao(arvore: ast.Module) -> list[ast.Import | ast.ImportFrom]:
    achados: list[ast.Import | ast.ImportFrom] = []
    for node in ast.walk(arvore):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            for interno in ast.walk(node):
                if isinstance(interno, ast.Import | ast.ImportFrom):
                    achados.append(interno)
    return achados


@pytest.mark.parametrize(("caminho", "lib"), CASOS)
def test_biblioteca_pesada_nao_e_importada_no_topo(caminho: str, lib: str) -> None:
    """Regra 1 da spec 104."""
    arvore = ast.parse((APP / caminho).read_text(encoding="utf-8"))
    ofensores = [node.lineno for node in _imports_de_topo(arvore.body) if lib in _raiz(node)]
    assert not ofensores, (
        f"app/{caminho} voltou a importar `{lib}` no topo (linha(s) {ofensores}). "
        "Spec 104: o import mora dentro da função que usa a biblioteca."
    )


@pytest.mark.parametrize(("caminho", "lib"), CASOS)
def test_biblioteca_pesada_continua_sendo_importada_em_algum_lugar(caminho: str, lib: str) -> None:
    """O outro lado da regra 1: um import apagado por engano também passaria no teste
    de cima. Este exige que a biblioteca continue chegando — dentro de uma função."""
    arvore = ast.parse((APP / caminho).read_text(encoding="utf-8"))
    assert any(lib in _raiz(node) for node in _imports_em_funcao(arvore)), (
        f"app/{caminho} não importa `{lib}` dentro de função nenhuma — "
        "ou o import sumiu, ou a biblioteca deixou de ser usada e a tabela da spec 104 "
        "precisa perder esta linha."
    )
