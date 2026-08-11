"""Spec 055, regra 5 — ciclo de fatura do cartão (cálculo puro, sem banco/relógio)."""

from datetime import date

import pytest

from app.core.dates import card_cycle_range


@pytest.mark.parametrize(
    ("cycle_day", "today", "expected_start", "expected_end"),
    [
        # Hoje já passou do fechamento do mês: ciclo começou neste mês.
        (10, date(2026, 8, 15), date(2026, 8, 10), date(2026, 9, 9)),
        # Hoje ainda não chegou no fechamento deste mês: ciclo começou no mês anterior.
        (10, date(2026, 8, 5), date(2026, 7, 10), date(2026, 8, 9)),
        # No dia exato do fechamento, o novo ciclo já começou.
        (10, date(2026, 8, 10), date(2026, 8, 10), date(2026, 9, 9)),
        # Regra 5: dia 31 num mês curto (fevereiro, não bissexto) vira o último dia.
        (31, date(2026, 2, 15), date(2026, 1, 31), date(2026, 2, 27)),
        # 2028 é bissexto — fevereiro tem 29 dias.
        (31, date(2028, 2, 15), date(2028, 1, 31), date(2028, 2, 28)),
        # Dezembro → janeiro: o ano vira junto.
        (20, date(2026, 12, 25), date(2026, 12, 20), date(2027, 1, 19)),
    ],
)
def test_card_cycle_range(
    cycle_day: int, today: date, expected_start: date, expected_end: date
) -> None:
    start, end = card_cycle_range(cycle_day, today)
    assert start == expected_start
    assert end == expected_end
