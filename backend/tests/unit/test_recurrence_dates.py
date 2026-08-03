"""Spec 034 §7 — cálculo puro das datas de recorrência (sem banco, sem relógio).

Os casos de borda de calendário são o coração da spec: dia 31 em mês curto (regra 3),
última semana em mês de 4 e de 5 semanas (regra 4), quinzenal = 14 dias corridos
(regra 5) e 29/02 anual. O frontend (features/posts/recurrence.ts) espelha esta
tabela nos testes do RecurrencePreview.
"""

from datetime import date

import pytest

from app.domain.posts.models import RecurrencePeriod as P
from app.domain.posts.models import RecurrenceWeek as W
from app.domain.posts.recurrence import next_occurrence, preview_occurrences


@pytest.mark.parametrize(
    ("period", "anchor", "current", "expected"),
    [
        # As 8 periodicidades sobre a mesma âncora (regra-base da spec).
        (P.DIARIA, date(2026, 8, 10), date(2026, 8, 10), date(2026, 8, 11)),
        (P.SEMANAL, date(2026, 8, 10), date(2026, 8, 10), date(2026, 8, 17)),
        (P.QUINZENAL, date(2026, 8, 10), date(2026, 8, 10), date(2026, 8, 24)),
        (P.MENSAL, date(2026, 8, 10), date(2026, 8, 10), date(2026, 9, 10)),
        (P.BIMESTRAL, date(2026, 8, 10), date(2026, 8, 10), date(2026, 10, 10)),
        (P.TRIMESTRAL, date(2026, 8, 10), date(2026, 8, 10), date(2026, 11, 10)),
        (P.SEMESTRAL, date(2026, 8, 10), date(2026, 8, 10), date(2027, 2, 10)),
        (P.ANUAL, date(2026, 8, 10), date(2026, 8, 10), date(2027, 8, 10)),
    ],
)
def test_oito_periodicidades(period: P, anchor: date, current: date, expected: date) -> None:
    assert next_occurrence(period, W.DIA_EXATO, anchor=anchor, current=current) == expected


def test_dia_31_cai_no_ultimo_dia_de_fevereiro_e_volta_ao_31_em_marco() -> None:
    # Regra 3: dia 31 em fevereiro clampa no último dia do mês, NUNCA cai em março…
    anchor = date(2026, 1, 31)
    feb = next_occurrence(P.MENSAL, W.DIA_EXATO, anchor=anchor, current=date(2026, 1, 31))
    assert feb == date(2026, 2, 28)
    # …e como o dia vem da ÂNCORA (não da ocorrência clampada), março volta ao 31.
    mar = next_occurrence(P.MENSAL, W.DIA_EXATO, anchor=anchor, current=feb)
    assert mar == date(2026, 3, 31)


def test_ultima_semana_resolve_em_mes_de_4_e_de_5_semanas() -> None:
    # Regra 4: segundas de jan/2026 = 5, 12, 19, 26 (4 ocorrências); as de mar/2026 =
    # 2, 9, 16, 23, 30 (5 ocorrências). A "última semana" acompanha as duas formas.
    anchor = date(2026, 1, 5)  # uma segunda-feira
    assert next_occurrence(P.MENSAL, W.ULTIMA, anchor=anchor, current=date(2026, 1, 26)) == date(
        2026, 2, 23
    )
    assert next_occurrence(P.MENSAL, W.ULTIMA, anchor=anchor, current=date(2026, 2, 23)) == date(
        2026, 3, 30
    )


@pytest.mark.parametrize(
    ("repeat_on", "expected"),
    [
        # Âncora numa terça (ago/2026 tem terças 4, 11, 18, 25); set/2026 começa numa
        # terça, então 1ª = dia 1, 2ª = dia 8, 3ª = dia 15.
        (W.PRIMEIRA, date(2026, 9, 1)),
        (W.SEGUNDA, date(2026, 9, 8)),
        (W.TERCEIRA, date(2026, 9, 15)),
    ],
)
def test_semanas_ordinais_do_mes(repeat_on: W, expected: date) -> None:
    anchor = date(2026, 8, 4)  # uma terça-feira
    assert next_occurrence(P.MENSAL, repeat_on, anchor=anchor, current=date(2026, 8, 4)) == expected


def test_quinzenal_e_14_dias_corridos_mesmo_cruzando_o_mes() -> None:
    # Regra 5: quinzenal ≠ "duas vezes por mês" — sempre +14 dias corridos.
    assert next_occurrence(
        P.QUINZENAL, W.DIA_EXATO, anchor=date(2026, 2, 20), current=date(2026, 2, 20)
    ) == date(2026, 3, 6)


def test_anual_em_29_de_fevereiro_clampa_nos_anos_comuns() -> None:
    # 29/02 só existe em ano bissexto — nos demais cai em 28/02 (mesma regra 3).
    anchor = date(2024, 2, 29)
    current = anchor
    assert next_occurrence(P.ANUAL, W.DIA_EXATO, anchor=anchor, current=current) == date(
        2025, 2, 28
    )
    current = date(2025, 2, 28)
    assert next_occurrence(P.ANUAL, W.DIA_EXATO, anchor=anchor, current=current) == date(
        2026, 2, 28
    )
    current = date(2027, 2, 28)
    # 2028 é bissexto de novo — a âncora preservada faz a série voltar ao 29.
    assert next_occurrence(P.ANUAL, W.DIA_EXATO, anchor=anchor, current=current) == date(
        2028, 2, 29
    )


def test_repeat_on_nao_se_aplica_as_periodicidades_por_dia() -> None:
    # ULTIMA numa série semanal é ignorada — a semana anda +7 dias de qualquer jeito.
    for repeat_on in W:
        assert next_occurrence(
            P.SEMANAL, repeat_on, anchor=date(2026, 8, 10), current=date(2026, 8, 10)
        ) == date(2026, 8, 17)


def test_preview_respeita_until_date_e_max_occurrences() -> None:
    # Regra 6: a série encerra pelo que vier primeiro — e o template já conta como
    # a 1ª ocorrência (occurrences_created=1).
    weekly = preview_occurrences(
        P.SEMANAL, W.DIA_EXATO, anchor=date(2026, 8, 10), start=date(2026, 8, 10), count=5
    )
    assert weekly == [
        date(2026, 8, 17),
        date(2026, 8, 24),
        date(2026, 8, 31),
        date(2026, 9, 7),
        date(2026, 9, 14),
    ]
    until = preview_occurrences(
        P.SEMANAL,
        W.DIA_EXATO,
        anchor=date(2026, 8, 10),
        start=date(2026, 8, 10),
        count=5,
        until_date=date(2026, 8, 30),
    )
    assert until == [date(2026, 8, 17), date(2026, 8, 24)]
    capped = preview_occurrences(
        P.SEMANAL,
        W.DIA_EXATO,
        anchor=date(2026, 8, 10),
        start=date(2026, 8, 10),
        count=5,
        max_occurrences=3,
    )
    # max=3 contando o template → só mais 2 ocorrências cabem na série.
    assert capped == [date(2026, 8, 17), date(2026, 8, 24)]
