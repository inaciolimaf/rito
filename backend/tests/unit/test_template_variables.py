"""Engine de variáveis (spec 066, §8) — extenso e `resolve_content` puros, sem
banco: cobrem as regras 4/5/6 sem pagar o custo de uma query."""

from datetime import date
from decimal import Decimal

from app.domain.templates.variables import (
    format_date_extenso,
    format_money_extenso,
    resolve_content,
)


def test_extenso_de_data_usa_primeiro_no_dia_1() -> None:
    assert format_date_extenso(date(2026, 8, 1)) == "primeiro de agosto de dois mil e vinte e seis"


def test_extenso_de_data_cardinal_nos_demais_dias() -> None:
    assert format_date_extenso(date(2026, 8, 20)) == "vinte de agosto de dois mil e vinte e seis"


def test_extenso_de_dinheiro_com_reais_e_centavos() -> None:
    result = format_money_extenso(Decimal("1234.56"))
    assert "reais" in result
    assert "cinquenta e seis centavos" in result


def test_extenso_de_dinheiro_valor_inteiro_sem_centavos_residuais() -> None:
    result = format_money_extenso(Decimal("1.00"))
    assert result == "um real"


def test_resolve_content_substitui_variavel_conhecida() -> None:
    html, missing = resolve_content(
        "<p>Olá {{cliente.nome_completo}}</p>", {"cliente.nome_completo": "Maria Silva"}
    )
    assert html == "<p>Olá Maria Silva</p>"
    assert missing == []


def test_resolve_content_marca_variavel_desconhecida_sem_quebrar_as_outras() -> None:
    html, missing = resolve_content(
        "<p>{{cliente.nome_completo}} — {{cliente.campo_inventado}}</p>",
        {"cliente.nome_completo": "Maria Silva"},
    )
    assert "Maria Silva" in html
    assert '<mark data-missing="true">{{cliente.campo_inventado}}</mark>' in html
    assert missing == ["cliente.campo_inventado"]


def test_resolve_content_variavel_sem_dado_vira_mark_e_e_reportada() -> None:
    html, missing = resolve_content("<p>{{processo.numero_cnj}}</p>", {"processo.numero_cnj": None})
    assert '<mark data-missing="true">{{processo.numero_cnj}}</mark>' in html
    assert missing == ["processo.numero_cnj"]


def test_resolve_content_texto_fora_do_padrao_fica_intocado() -> None:
    html, missing = resolve_content("<p>{{ isso não é variável }}</p>", {})
    assert html == "<p>{{ isso não é variável }}</p>"
    assert missing == []
