"""Spec 038, regra 3 — dias úteis: sábado/domingo e feriados nacionais não contam.
Casos em tabela sobre datas FIXAS (não dependem do dia em que o teste roda)."""

from datetime import date

import pytest

from app.domain.workflows.business_days import add_business_days, is_business_day

_NATAL_2026 = date(2026, 12, 25)  # sexta-feira
_CARNAVAL_TER_2027 = date(2027, 2, 9)


@pytest.mark.parametrize(
    ("start", "offset", "expected"),
    [
        # Segunda +1 → terça (semana normal).
        (date(2026, 8, 10), 1, date(2026, 8, 11)),
        # Sexta +1 → segunda (pula sábado e domingo).
        (date(2026, 8, 7), 1, date(2026, 8, 10)),
        # Sábado +1 → segunda (o disparo no fim de semana não conta).
        (date(2026, 8, 8), 1, date(2026, 8, 10)),
        # Segunda +5 → segunda seguinte (uma semana útil inteira).
        (date(2026, 8, 10), 5, date(2026, 8, 17)),
        # Sexta +2 → terça (sábado e domingo no meio do caminho).
        (date(2026, 8, 7), 2, date(2026, 8, 11)),
    ],
)
def test_dias_uteis_pulam_fim_de_semana(start: date, offset: int, expected: date) -> None:
    assert add_business_days(start, offset, holidays=set()) == expected


def test_dias_uteis_pulam_feriado_nacional() -> None:
    # Quinta 24/12 +1: 25/12 é feriado (sexta), 26–27 fim de semana → segunda 28/12.
    assert add_business_days(date(2026, 12, 24), 1, holidays={_NATAL_2026}) == date(2026, 12, 28)
    # Dois feriados seguidos (Carnaval seg+ter): sexta anterior +1 → quarta de cinzas.
    assert add_business_days(
        date(2027, 2, 5), 1, holidays={date(2027, 2, 8), _CARNAVAL_TER_2027}
    ) == date(2027, 2, 10)


def test_offset_zero_e_o_proprio_dia() -> None:
    # Regra 4: 0 = hoje, mesmo em fim de semana ou feriado — "hoje" não desliza.
    assert add_business_days(date(2026, 8, 8), 0, holidays=set()) == date(2026, 8, 8)
    assert add_business_days(_NATAL_2026, 0, holidays={_NATAL_2026}) == _NATAL_2026


def test_offset_negativo_e_erro() -> None:
    with pytest.raises(ValueError, match="negativo"):
        add_business_days(date(2026, 8, 10), -1, holidays=set())


def test_is_business_day() -> None:
    assert is_business_day(date(2026, 8, 10), set())  # segunda
    assert not is_business_day(date(2026, 8, 9), set())  # domingo
    assert not is_business_day(_NATAL_2026, {_NATAL_2026})  # feriado mesmo em dia de semana
