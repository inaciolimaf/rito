"""Cálculo de dias úteis (spec 038, regra 3) — isolado e puro de propósito: a spec 086
(prazos processuais) vai reutilizar esta mesma função (ver §10 da spec)."""

from collections.abc import Collection
from datetime import date, timedelta


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
