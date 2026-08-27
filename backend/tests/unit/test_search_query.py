"""Detecção do tipo de busca (spec 096, regra 2).

Unitário porque é a decisão mais importante da feature e não precisa de banco: quem
digita 11 dígitos sabe exatamente quem procura, e devolver resultado por relevância
textual nesse caso seria absurdo.
"""

import pytest

from app.domain.search.query import QueryKind, parse_query, to_tsquery_input


@pytest.mark.parametrize("raw", ["", " ", "a", " x "])
def test_menos_de_dois_caracteres_e_curto_demais(raw: str) -> None:
    assert parse_query(raw).kind is QueryKind.TOO_SHORT


@pytest.mark.parametrize(
    "raw", ["11144477735", "111.444.777-35", "11222333000181", "11.222.333/0001-81"]
)
def test_cpf_e_cnpj_com_e_sem_mascara_viram_busca_exata(raw: str) -> None:
    parsed = parse_query(raw)

    assert parsed.kind is QueryKind.DOCUMENT
    assert parsed.digits.isdigit()
    assert parsed.is_exact


@pytest.mark.parametrize("raw", ["00012345620268260100", "0001234-56.2026.8.26.0100"])
def test_cnj_com_e_sem_mascara_vira_busca_por_processo(raw: str) -> None:
    parsed = parse_query(raw)

    assert parsed.kind is QueryKind.PROCESS_NUMBER
    assert parsed.digits == "00012345620268260100"


@pytest.mark.parametrize("raw", ["ana", "ana maria", "pasta 2026", "joão"])
def test_o_resto_e_full_text(raw: str) -> None:
    assert parse_query(raw).kind is QueryKind.FULL_TEXT


def test_numero_solto_que_nao_e_documento_nem_cnj_e_full_text() -> None:
    """Uma pasta chamada "2026" é texto, não documento."""
    assert parse_query("2026").kind is QueryKind.FULL_TEXT


def test_ultimo_termo_vira_prefixo() -> None:
    """Quem digita "Mar" espera achar "Marina" antes de terminar de escrever."""
    assert to_tsquery_input("mar") == "mar:*"
    assert to_tsquery_input("ana maria") == "ana & maria:*"


def test_operadores_do_tsquery_nao_passam_do_campo_de_busca() -> None:
    """`&`, `|` e `!` vindos do usuário viram erro de sintaxe do Postgres — o campo de
    busca não pode ser um console de consulta."""
    assert to_tsquery_input("ana & !x") == "ana & x:*"
    assert to_tsquery_input("a|b") == "a b:*"
    assert to_tsquery_input("!!!") == ""
