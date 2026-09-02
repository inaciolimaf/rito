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

## Por que 30

Trinta linhas é o que cabe numa tela sem rolar — a distância em que um revisor segura a
função inteira na cabeça enquanto lê a última linha. É o alvo que a 121 pedia desde o começo;
50 e 40 foram degraus de execução, não destinos.

O corte veio em três degraus (specs 121 → 122 → 123), cada um deixando o gate LIGADO e verde:
29 funções reestruturadas para chegar a zero acima de 50, 30 para chegar a zero acima de 40,
e 101 para chegar a zero acima de 30.

Como todo teto do projeto: **este número só desce**.

## Por que existem exceções agora, e não existiam em 50

Duas funções acima de 40 são mapeadores de campo puros: um `return Response(...)` com 40 e
com 24 atribuições `campo=objeto.campo`, sem ramo nem cálculo. Cortá-los ao meio produziria
um `_parte_um`/`_parte_dois` que ninguém conseguiria nomear pelo que faz — indireção sem
significado, que é exatamente o que o teto existe para evitar. O tamanho deles é o tamanho
do schema, e encolhe quando o schema encolher.
"""

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
APP = BACKEND / "app"
RAIZ = BACKEND.parent

TETO_DE_LINHAS = 30

# Exceções versionadas (spec 121, regra 5): teto de 5 no projeto, cada uma justificada.
# Duas em uso desde o degrau 2 (spec 122), as duas pelo mesmo motivo: mapeador de campo puro.
# A 123 não precisou de uma terceira: dos cinco candidatos que a varredura por AST apontou,
# quatro tinham um GRUPO de campos com nome próprio a extrair (as datas do ciclo de vida, os
# valores financeiros, os intervalos de filtro) e só estes dois não têm.
EXCECOES: dict[str, str] = {
    "app/domain/customers/router.py::_customer_to_response": (
        "42 linhas contra o teto de 30. Mapeador puro: um único `return CustomerResponse(...)` "
        "com 40 campos `campo=customer.campo`, sem ramo, laço nem cálculo — classificado por "
        "AST, não a olho. O tamanho é o do schema de contato (spec 019), não da lógica, e "
        "encolhe quando o schema encolher."
    ),
    "app/domain/posts/router.py::_to_response": (
        "41 linhas contra o teto de 30. Mapeador puro DEPOIS da guarda: a parte com decisão "
        "(tarefa privada vista por terceiro) já saiu em `_redacted_response`; o que sobra é "
        "`return PostResponse(...)` com 24 campos. Encolhe quando o schema de tarefa "
        "encolher, não antes."
    ),
}


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
    """Regra 1 da 121, no degrau final (teto 30, spec 123).

    Uma função acima do teto quase nunca precisa de uma linha a menos: precisa de um bloco
    com nome. Nas 160 reestruturadas ao longo dos três degraus, o bloco extraído sempre teve
    um nome óbvio — e a função que sobrou passou a dizer o que faz na primeira tela. As duas
    únicas exceções são mapeadores de campo, onde não existe bloco a nomear.
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
