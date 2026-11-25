"""O que o modelo escreveu × o que o código entendeu (spec 133 §5, regras 6 e 7).

`parse_model_output` é a fronteira entre linguagem e aritmética da spec 086 — e é onde
uma leitura tolerante demais vira uma data errada apresentada como certa. Os testes aqui
são de mesa: nenhum banco, nenhum modelo, só a tradução.
"""

from datetime import date

import pytest

from app.domain.publications.analysis import (
    MAX_DEADLINE_DAYS,
    ParsedAnalysis,
    parse_model_output,
)
from app.domain.publications.deadline import compute_deadline


def _saida(**campos: object) -> ParsedAnalysis:
    import json

    return parse_model_output(json.dumps({"summary": "resumo", **campos}, ensure_ascii=False))


@pytest.mark.parametrize(
    ("escrito", "lido"),
    [
        ("corridos", "corridos"),
        ("dias corridos", "corridos"),
        ("CORRIDOS", "corridos"),
        ("uteis", "uteis"),
        ("úteis", "uteis"),
        ("dias úteis", "uteis"),
        ("DIAS ÚTEIS", "uteis"),
    ],
)
def test_a_especie_do_prazo_e_lida_pelo_radical_e_nao_pelo_literal(escrito: str, lido: str) -> None:
    """Spec 133: só os dois literais exatos eram aceitos, e o resto virava `None`.

    `"úteis"` com acento e `"dias corridos"` são as duas formas mais naturais para um
    modelo que responde em português — o prompt pede `'uteis'`/`'corridos'`, e nada obriga
    o modelo a obedecer. Cada uma delas caía em `None`, e `compute_deadline` traduzia
    `None` em dias ÚTEIS, que é a contagem MAIS LONGA.
    """
    assert _saida(deadline_days=15, deadline_kind=escrito).deadline_kind == lido


@pytest.mark.parametrize("escrito", ["semanas", "", "sei lá", "1", None, 15])
def test_especie_que_nao_da_para_ler_continua_desconhecida(escrito: object) -> None:
    """O reconhecimento pelo radical não pode virar adivinhação: o que não contém nenhum
    dos dois radicais continua `None` — e `None` agora significa "não sei"."""
    assert _saida(deadline_days=15, deadline_kind=escrito).deadline_kind is None


@pytest.mark.parametrize(
    ("escrito", "lido"),
    [(15, 15), (15.0, 15), ("15", 15), (" 15 ", 15), ("15.0", 15), (1, 1)],
)
def test_dias_de_prazo_sao_lidos_como_numero_e_nao_como_texto(escrito: object, lido: int) -> None:
    """Spec 133: a leitura era `str(dias).isdigit()`, que descarta `15.0`.

    Float é forma perfeitamente válida em JSON — e a que qualquer serializador produz para
    um inteiro que passou por ponto flutuante. O prazo sumia inteiro, sem registro nenhum:
    a intimação chegava à tela com o campo vazio e ninguém sabia que o modelo tinha lido.
    """
    assert _saida(deadline_days=escrito, deadline_kind="corridos").deadline_days == lido


@pytest.mark.parametrize(
    "escrito", ["15 dias", "quinze", 0, -5, MAX_DEADLINE_DAYS + 1, True, None, {"dias": 15}]
)
def test_dias_fora_da_faixa_ou_ilegiveis_voltam_vazios(escrito: object) -> None:
    """Ler número não é aceitar qualquer número: `0`, negativo e 4.000 são erro de leitura,
    não prazo exótico — e um prazo de 4.000 dias vira uma data que ninguém confere.

    `True` está na lista porque `bool` é `int` em Python: sem a checagem explícita,
    `deadline_days=true` viraria um prazo de um dia.
    """
    assert _saida(deadline_days=escrito, deadline_kind="corridos").deadline_days is None


def test_a_diferenca_que_a_especie_faz_e_de_seis_dias() -> None:
    """O tamanho do erro, medido — é o que justifica a spec tratar isto como defeito.

    Disponibilização em 08/09/2026, prazo de 15 dias, sem feriado. Em dias corridos o
    vencimento é 24/09; contado como úteis, 30/09. Seis dias depois do vencimento legal,
    apresentados com a mesma cara de resposta.
    """
    disponibilizacao = date(2026, 9, 8)
    corridos = compute_deadline(
        availability_date=disponibilizacao, days=15, kind="corridos", holidays=()
    )
    uteis = compute_deadline(availability_date=disponibilizacao, days=15, kind="uteis", holidays=())

    assert corridos == date(2026, 9, 24)
    assert uteis == date(2026, 9, 30)


def test_o_resto_da_leitura_continua_igual() -> None:
    """A tolerância do parser era a coisa certa e não foi mexida: JSON embrulhado em crase,
    campo faltando, texto solto — nada disso pode virar exceção (regra 5 da 086)."""
    parsed = parse_model_output('```json\n{"summary": "Sentença publicada."}\n```')

    assert parsed.summary == "Sentença publicada."
    assert parsed.deadline_days is None
    assert parsed.deadline_kind is None
    assert parsed.requires_action is False
