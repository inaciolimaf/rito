"""Divisão de indicador num lugar só (refatoração 080, alvo 3).

O valor destes casos é a distinção que o produto inteiro depende: zero é um
diagnóstico ("nenhum ganho"), `None` é a ausência dele ("nada para dividir") — e a UI
mostra os dois de formas diferentes.
"""

from decimal import Decimal

from app.core.ratios import safe_percentage, safe_ratio


def test_denominador_zero_ou_nulo_vira_none_nunca_zero() -> None:
    assert safe_ratio(10, 0) is None
    assert safe_ratio(10, None) is None
    assert safe_percentage(3, 0) is None
    # Numerador zero continua sendo zero — houve base de cálculo, o resultado é 0.
    assert safe_ratio(0, 4) == 0.0
    assert safe_percentage(0, 4) == 0.0


def test_arredondamento_acontece_uma_vez_no_fim() -> None:
    # 1/3 = 33,333…%: arredondar o quociente antes de multiplicar daria 33,0.
    assert safe_percentage(1, 3) == 33.3
    assert safe_ratio(1, 3) == 0.33
    assert safe_ratio(1, 3, digits=None) == 1 / 3


def test_aceita_decimal_do_banco() -> None:
    assert safe_ratio(Decimal("150.00"), 4) == 37.5
    assert safe_percentage(Decimal("1"), Decimal("8")) == 12.5
