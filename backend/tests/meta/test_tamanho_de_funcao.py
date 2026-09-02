"""Teto de linhas por função em `app/` (spec 121, degrau 1).

## Por que contagem LÍQUIDA

Contar linha bruta pune documentação. Este projeto tem densidade de comentário deliberada —
as justificativas dentro do código são metade do valor dele —, e um gate que incentive
apagá-las é pior que gate nenhum.

A diferença foi medida antes de escolher: pela contagem bruta, 224 funções passavam de 30;
pela líquida, 134. **Noventa funções passavam apenas por assinatura multilinha e
docstring.** Daí a regra: conta-se do primeiro statement executável ao último, com
docstring, decoradores e assinatura de fora.

## Por que o Ruff não faz isso

`PLR0915` conta STATEMENTS, que é outra coisa: um `dict` literal de 40 linhas é um
statement só, e está certo que seja — para aquele gate. Este mede o que um revisor enxerga
sem rolar a tela, e não existe regra do Ruff para isso.

## Por que 50, e não 30

A spec pede 30 e a Nota de execução dela prevê o corte em degraus (50 → 40 → 30), cada um
deixando o gate LIGADO e verde. Este é o primeiro: 29 funções foram reestruturadas para
chegar a zero acima de 50. A distribuição do que falta está na §12 da spec — 16 acima de
45, 32 acima de 40, 117 acima de 30.

Como todo teto do projeto: **este número só desce**.
"""

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
APP = BACKEND / "app"
RAIZ = BACKEND.parent

TETO_DE_LINHAS = 50

# Exceções versionadas (spec 121, regra 5): teto de 5 no projeto, cada uma justificada.
# Vazio no degrau 1 — nenhuma função precisou de exceção para caber em 50.
EXCECOES: dict[str, str] = {}


def linhas_liquidas(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Do primeiro statement executável ao último. Docstring não conta."""
    corpo = fn.body
    if (
        corpo
        and isinstance(corpo[0], ast.Expr)
        and isinstance(corpo[0].value, ast.Constant)
        and isinstance(corpo[0].value.value, str)
    ):
        corpo = corpo[1:]
    if not corpo:
        return 0
    return (corpo[-1].end_lineno or corpo[-1].lineno) - corpo[0].lineno + 1


def _funcoes_acima_do_teto() -> list[tuple[str, int]]:
    fora: list[tuple[str, int]] = []
    for arquivo in sorted(APP.rglob("*.py")):
        arvore = ast.parse(arquivo.read_text(), filename=str(arquivo))
        for fn in ast.walk(arvore):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            n = linhas_liquidas(fn)
            if n <= TETO_DE_LINHAS:
                continue
            chave = f"{arquivo.relative_to(BACKEND)}::{fn.name}"
            if chave not in EXCECOES:
                fora.append((chave, n))
    return fora


def test_nenhuma_funcao_de_app_passa_do_teto() -> None:
    """Regra 1 da 121, no degrau 1 (teto 50).

    Uma função acima do teto quase nunca precisa de uma linha a menos: precisa de um bloco
    com nome. Nas 29 desta spec, o bloco extraído sempre tinha um nome óbvio — e a função
    que sobrou passou a dizer o que faz na primeira tela.
    """
    fora = [f"{chave} ({n} linhas)" for chave, n in _funcoes_acima_do_teto()]
    assert fora == [], (
        f"função de app/ acima de {TETO_DE_LINHAS} linhas líquidas de corpo. Extraia um "
        "bloco com nome — não apague comentário, que a contagem já ignora:\n  " + "\n  ".join(fora)
    )


def test_excecoes_dentro_do_teto_e_justificadas() -> None:
    """Regra 5: no máximo 5 exceções, cada uma com justificativa.

    Se a implementação precisar da sexta, o teto está errado para este código — e essa
    conclusão vale mais que forçar o número.
    """
    assert len(EXCECOES) <= 5, (
        f"{len(EXCECOES)} exceções de tamanho de função, teto é 5: " f"{sorted(EXCECOES)}"
    )
    sem_motivo = sorted(chave for chave, motivo in EXCECOES.items() if len(motivo.strip()) < 20)
    assert sem_motivo == [], "exceção de tamanho sem justificativa escrita:\n  " + "\n  ".join(
        sem_motivo
    )


def test_excecao_que_nao_e_mais_necessaria_reprova() -> None:
    """Exceção para função que hoje cabe no teto é ruído que parece proteção.

    Mesmo princípio do `RUF100` (spec 113): supressão morta documenta um problema que não
    existe e treina quem lê a ignorar as que seguram algo.
    """
    obsoletas: list[str] = []
    for arquivo in sorted(APP.rglob("*.py")):
        arvore = ast.parse(arquivo.read_text(), filename=str(arquivo))
        for fn in ast.walk(arvore):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            chave = f"{arquivo.relative_to(BACKEND)}::{fn.name}"
            if chave in EXCECOES and linhas_liquidas(fn) <= TETO_DE_LINHAS:
                obsoletas.append(chave)
    assert (
        obsoletas == []
    ), "exceção de tamanho para função que já cabe no teto — remova:\n  " + "\n  ".join(obsoletas)
