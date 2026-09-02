"""Nome de identificador é inglês (CLAUDE.md §9), e agora existe quem cobre.

## Por que este arquivo nasceu na spec 124, e não na 120

A spec 120 renomeou 88 símbolos privados para inglês e verificou o trabalho por AST: para
cada um dos 45 arquivos do mapa, o conjunto de identificadores de antes com o mapa aplicado
era idêntico ao de depois. A verificação era correta — e provava a coisa errada.

Ela provava que **o mapa foi aplicado certo**. Não que **o mapa estava completo**. Oito
auxiliares privados ficaram de fora, seis deles no mesmo arquivo (`core/migrations.py`, que
simplesmente não entrou na lista), e ninguém percebeu por três specs. É a dívida 40.

E foram ONZE, não oito: a varredura manual que abriu a dívida 40 usou uma expressão regular
sobre nomes e achou oito; este teste, rodando pela primeira vez, achou mais três
(`_resolve_escritorio`, `_resolve_usuario`, `build_payload` — este último criado pela própria
spec 123, por imitação do arquivo em volta). O gate encontrou o que quem o escreveu não tinha
encontrado, no primeiro minuto de vida. É o argumento inteiro a favor de gates.

A pergunta que faltava não era «o mapa foi aplicado?», era **«sobrou alguma função privada de
`app/` cujo nome pareça português?»**. Esta é a diferença entre verificar a entrada e varrer o
universo, e é a razão de este teste existir: sem ele, a dívida volta na próxima spec que
editar um arquivo onde o padrão local ainda fosse português.

A 123 quase escreveu um nono, por imitação do que estava em volta (`_esperar_a_vez`, virou
`_wait_for_turn` antes do commit). Um arquivo consistentemente em português é uma armadilha
para quem edita nele — e o gate é o que impede a armadilha de se armar de novo.

## Como ele decide o que é português

Por **lista de palavras**, não por heurística de morfologia. Uma heurística que tentasse
adivinhar pela terminação (`-ao`, `-cao`, `-es`) reprovaria `_relation`, `_action`, `_names`
e `_files` — e um gate que dá falso positivo em inglês legítimo é um gate que as pessoas
aprendem a contornar.

A lista tem só palavras que **não existem em inglês** e aparecem em código brasileiro. Ela
cresce quando alguém tentar um nome novo em português: acrescentar a palavra é uma linha, e o
teste passa a pegar a família inteira.

Docstrings e comentários continuam em português, como o §9 manda — este teste lê NOMES.
"""

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
APP = BACKEND / "app"

# Palavras que não existem em inglês e aparecem em nome de identificador brasileiro. Só
# radicais inequívocos: `data` está fora de propósito (é inglês também), `tipo` está fora
# porque `type` já cobre o caso e ninguém escreveria `tipo` sem escrever mais alguma coisa.
PALAVRAS_PT = frozenset(
    {
        "acao",
        "acoes",
        "alteracao",
        "alteracoes",
        "aplicar",
        "arquivo",
        "atual",
        "buscar",
        "cadastro",
        "chave",
        "criar",
        "destravar",
        "dono",
        "escritorio",
        "esperar",
        "listar",
        "montar",
        "nome",
        "obter",
        "permitidas",
        "permitido",
        "permitidos",
        "processo",
        "quem",
        "relacao",
        "relacoes",
        "salvar",
        "sincrono",
        "tentar",
        "travar",
        "usuario",
        "valor",
        "versao",
        "vez",
    }
)

# Exceções: nomes que a lista pegaria e que estão certos. Vazio hoje — cada entrada aqui
# precisa dizer por que a palavra portuguesa é a certa naquele lugar.
EXCECOES: dict[str, str] = {}


def _palavras(nome: str) -> set[str]:
    """As partes de um `snake_case`, sem o sublinhado inicial dos privados."""
    return {parte for parte in nome.strip("_").split("_") if parte}


def _nomes_definidos() -> list[tuple[str, str]]:
    """`(arquivo::nome, nome)` de toda função e classe definida em `app/`."""
    definidos: list[tuple[str, str]] = []
    for arquivo in sorted(APP.rglob("*.py")):
        arvore = ast.parse(arquivo.read_text(), filename=str(arquivo))
        for no in ast.walk(arvore):
            if isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                definidos.append((f"{arquivo.relative_to(BACKEND)}::{no.name}", no.name))
    return definidos


def test_nenhuma_funcao_de_app_tem_nome_em_portugues() -> None:
    """Regra do §9, cobrada pela primeira vez — a dívida 40 é o que acontece sem isto."""
    fora = [
        f"{chave} (palavra: {', '.join(sorted(_palavras(nome) & PALAVRAS_PT))})"
        for chave, nome in _nomes_definidos()
        if _palavras(nome) & PALAVRAS_PT and chave not in EXCECOES
    ]
    assert fora == [], (
        "identificador em português em `app/` — o §9 pede inglês no nome e português na "
        "docstring:\n  " + "\n  ".join(fora)
    )


def test_a_lista_de_palavras_pega_o_que_a_divida_40_encontrou() -> None:
    """Prova que o gate MORDE, com os nomes reais que escaparam da spec 120.

    Sem este teste, esvaziar `PALAVRAS_PT` deixaria o gate verde e inútil — o mesmo defeito
    da verificação da 120, agora dentro do teste que existe para consertá-la.
    """
    escaparam_da_120 = [
        "_quem_sou_eu",
        "_anotar_dono",
        "_tentar_travar",
        "_destravar",
        "_versao_atual",
        "_aplicar_sincrono",
        "_relacoes_permitidas",
        "_aplicar_alteracoes",
        # Os três que só o gate achou — a varredura manual da dívida 40 passou por eles.
        "_resolve_escritorio",
        "_resolve_usuario",
        "montar",
    ]
    nao_pegos = [nome for nome in escaparam_da_120 if not _palavras(nome) & PALAVRAS_PT]
    assert nao_pegos == [], (
        "a lista de palavras deixou de pegar nomes que a dívida 40 encontrou de verdade:\n  "
        + "\n  ".join(nao_pegos)
    )


def test_excecao_que_nao_e_mais_necessaria_reprova() -> None:
    """Exceção para nome que hoje já está em inglês é ruído que parece proteção.

    Mesmo princípio do `RUF100` (spec 113) e do teto de tamanho de função (spec 121):
    supressão morta documenta um problema que não existe e treina quem lê a ignorar as que
    seguram algo.
    """
    definidos = dict(_nomes_definidos())
    obsoletas = [
        chave
        for chave in EXCECOES
        if chave in definidos and not _palavras(definidos[chave]) & PALAVRAS_PT
    ]
    assert obsoletas == [], "exceção de idioma para nome que já está em inglês — remova:\n  " + (
        "\n  ".join(obsoletas)
    )
