"""Módulo único de datas do Rito (spec 040, alvo 1) — puro: sem banco, sem relógio,
sem framework. Cada função recebe tudo de que precisa por parâmetro.

Aqui moram as três lógicas de calendário que nasceram separadas:

- **dias úteis e feriados** (spec 038 — workflows);
- **próxima ocorrência de recorrência** (spec 034 — séries de tarefas), com os enums
  `RecurrencePeriod`/`RecurrenceWeek` (os valores persistidos no PG enum mudam nunca —
  só a casa da classe Python mudou; `app/domain/posts/models.py` re-exporta);
- **aritmética de mês** (fim de mês, início do mês seguinte/anterior, n-ésima e última
  semana do mês) — antes duplicada em lawsuits/stats.py e taskscore/repository.py.

Specs futuras DEVEM usar daqui em vez de recriar: 057 (parcelamento financeiro) usa
`add_business_days`/aritmética de mês; 086 (prazo processual) usa `add_business_days`.
"""

from calendar import monthrange
from collections.abc import Collection, Iterator
from datetime import date, timedelta
from enum import StrEnum


class RecurrencePeriod(StrEnum):
    """As 8 periodicidades da spec 034 §4 (ADVBOX: campo `recurrence`)."""

    DIARIA = "DIARIA"
    SEMANAL = "SEMANAL"
    QUINZENAL = "QUINZENAL"
    MENSAL = "MENSAL"
    BIMESTRAL = "BIMESTRAL"
    TRIMESTRAL = "TRIMESTRAL"
    SEMESTRAL = "SEMESTRAL"
    ANUAL = "ANUAL"


class RecurrenceWeek(StrEnum):
    """Os 5 modos de repetição no mês (ADVBOX: campo `repeat_on_week`) — só fazem
    diferença nas periodicidades mensais ou mais longas."""

    DIA_EXATO = "DIA_EXATO"
    PRIMEIRA = "PRIMEIRA"
    SEGUNDA = "SEGUNDA"
    TERCEIRA = "TERCEIRA"
    ULTIMA = "ULTIMA"


# ---------------------------------------------------------------------------
# Aritmética de mês
# ---------------------------------------------------------------------------


def month_end(year: int, month: int) -> date:
    """O último dia do mês — 28/29 em fevereiro, 30 ou 31 nos demais."""
    return date(year, month, monthrange(year, month)[1])


def next_month_start(month: date) -> date:
    """O dia 1 do mês seguinte ao mês de `month` (o dia de `month` é ignorado)."""
    first = month.replace(day=1)
    return date(first.year + (first.month == 12), first.month % 12 + 1, 1)


def previous_month_start(month: date) -> date:
    """O dia 1 do mês anterior ao mês de `month` (o dia de `month` é ignorado)."""
    return (month.replace(day=1) - timedelta(days=1)).replace(day=1)


def shift_month(year: int, month: int, months: int) -> tuple[int, int]:
    """(ano, mês) daqui a `months` meses — sem tocar no dia."""
    zero_based = month - 1 + months
    return year + zero_based // 12, zero_based % 12 + 1


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """A n-ésima ocorrência (1-based) do dia da semana no mês."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def last_weekday(year: int, month: int, weekday: int) -> date:
    """A última ocorrência do dia da semana no mês — resolve igual em meses de 4 e
    de 5 semanas (regra 4 da 034), porque parte do ÚLTIMO DIA do mês e anda para trás."""
    last = month_end(year, month)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


# ---------------------------------------------------------------------------
# Dias úteis (spec 038, regra 3)
# ---------------------------------------------------------------------------


def is_business_day(day: date, holidays: Collection[date]) -> bool:
    """Dia útil = não é sábado, nem domingo, nem feriado (nacional)."""
    return day.weekday() < 5 and day not in holidays


def add_business_days(start: date, offset: int, holidays: Collection[date]) -> date:
    """Avança `offset` dias úteis a partir de `start`.

    Regra 4: offset 0 é o próprio dia do disparo, mesmo que caia em fim de semana ou
    feriado — "hoje" não desliza. Offset N ≥ 1 devolve o N-ésimo dia útil seguinte.
    """
    if offset < 0:
        raise ValueError("days_offset não pode ser negativo.")
    if offset == 0:
        return start
    current = start
    counted = 0
    while counted < offset:
        current += timedelta(days=1)
        if is_business_day(current, holidays):
            counted += 1
    return current


# ---------------------------------------------------------------------------
# Recorrência (spec 034 §7)
#
# A âncora é a `scheduled_date` do post template (a primeira ocorrência): o dia do mês
# e o dia da semana da série vêm dela, então um "todo dia 31" que cai em fevereiro
# (regra 3) volta para 31 em março em vez de grudar no dia 28.
# ---------------------------------------------------------------------------

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
    year, month = shift_month(current.year, current.month, months)
    if repeat_on is RecurrenceWeek.DIA_EXATO:
        # Regra 3: o dia vem da ÂNCORA (não da ocorrência anterior, que pode ter
        # clampado) — "todo dia 31" volta a ser 31 em março depois de fevereiro.
        day = min(anchor.day, monthrange(year, month)[1])
        return date(year, month, day)
    if repeat_on is RecurrenceWeek.ULTIMA:
        return last_weekday(year, month, anchor.weekday())
    return nth_weekday(year, month, anchor.weekday(), _WEEK_ORDINAL[repeat_on])


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
