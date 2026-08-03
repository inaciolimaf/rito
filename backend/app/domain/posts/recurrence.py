"""Cálculo puro de datas de recorrência (spec 034 §7) — sem banco, sem relógio.

A âncora é a `scheduled_date` do post template (a primeira ocorrência): o dia do mês
e o dia da semana da série vêm dela, então um "todo dia 31" que cai em fevereiro
(regra 3) volta para 31 em março em vez de grudar no dia 28.
"""

from calendar import monthrange
from collections.abc import Iterator
from datetime import date, timedelta

from app.domain.posts.models import RecurrencePeriod, RecurrenceWeek

# Periodicidades por dia corrido — `repeat_on` não se aplica a elas (quinzenal é
# +14 dias corridos, regra 5, não "duas vezes por mês").
_DAYS_BY_PERIOD = {
    RecurrencePeriod.DIARIA: 1,
    RecurrencePeriod.SEMANAL: 7,
    RecurrencePeriod.QUINZENAL: 14,
}

_MONTHS_BY_PERIOD = {
    RecurrencePeriod.MENSAL: 1,
    RecurrencePeriod.BIMESTRAL: 2,
    RecurrencePeriod.TRIMESTRAL: 3,
    RecurrencePeriod.SEMESTRAL: 6,
    RecurrencePeriod.ANUAL: 12,
}

_WEEK_ORDINAL = {
    RecurrenceWeek.PRIMEIRA: 1,
    RecurrenceWeek.SEGUNDA: 2,
    RecurrenceWeek.TERCEIRA: 3,
}


def _shift_month(year: int, month: int, months: int) -> tuple[int, int]:
    """(ano, mês) daqui a `months` meses — sem tocar no dia."""
    zero_based = month - 1 + months
    return year + zero_based // 12, zero_based % 12 + 1


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """A n-ésima ocorrência (1-based) do dia da semana no mês."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """A última ocorrência do dia da semana no mês — resolve igual em meses de 4 e
    de 5 semanas (regra 4), porque parte do ÚLTIMO DIA do mês e anda para trás."""
    last = date(year, month, monthrange(year, month)[1])
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def next_occurrence(
    period: RecurrencePeriod,
    repeat_on: RecurrenceWeek,
    *,
    anchor: date,
    current: date,
) -> date:
    """A data seguinte a `current` na série ancorada em `anchor`.

    - DIARIA/SEMANAL/QUINZENAL: +1/+7/+14 dias corridos (regra 5).
    - Mensais com DIA_EXATO: mesmo dia do mês da âncora; mês curto clampa no último
      dia do mês (regra 3) — dia 31 em fevereiro vira 28/29, nunca 3 de março, e o
      29/02 anual cai em 28/02 nos anos não bissextos.
    - Mensais com PRIMEIRA/SEGUNDA/TERCEIRA/ULTIMA: a n-ésima (ou última) ocorrência
      do DIA DA SEMANA da âncora no mês alvo.
    """
    days = _DAYS_BY_PERIOD.get(period)
    if days is not None:
        return current + timedelta(days=days)

    months = _MONTHS_BY_PERIOD[period]
    year, month = _shift_month(current.year, current.month, months)
    if repeat_on is RecurrenceWeek.DIA_EXATO:
        # Regra 3: o dia vem da ÂNCORA (não da ocorrência anterior, que pode ter
        # clampado) — "todo dia 31" volta a ser 31 em março depois de fevereiro.
        day = min(anchor.day, monthrange(year, month)[1])
        return date(year, month, day)
    if repeat_on is RecurrenceWeek.ULTIMA:
        return _last_weekday(year, month, anchor.weekday())
    return _nth_weekday(year, month, anchor.weekday(), _WEEK_ORDINAL[repeat_on])


def preview_occurrences(
    period: RecurrencePeriod,
    repeat_on: RecurrenceWeek,
    *,
    anchor: date,
    start: date,
    count: int,
    until_date: date | None = None,
    max_occurrences: int | None = None,
    occurrences_created: int = 1,
) -> list[date]:
    """As próximas `count` datas a partir de `start` (exclusivo), já respeitando os
    limites da série (regra 6): até `until_date` e até completar `max_occurrences`."""
    dates: list[date] = []
    current = start
    created = occurrences_created
    while len(dates) < count:
        if max_occurrences is not None and created >= max_occurrences:
            break
        candidate = next_occurrence(period, repeat_on, anchor=anchor, current=current)
        if until_date is not None and candidate > until_date:
            break
        dates.append(candidate)
        current = candidate
        created += 1
    return dates


def iter_occurrences(
    period: RecurrencePeriod, repeat_on: RecurrenceWeek, *, anchor: date, start: date
) -> Iterator[date]:
    """Gerador infinito de datas a partir de `start` (exclusivo) — uso interno do
    worker; o chamador é quem para (limite da série ou data de referência)."""
    current = start
    while True:
        current = next_occurrence(period, repeat_on, anchor=anchor, current=current)
        yield current
