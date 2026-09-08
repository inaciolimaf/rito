"""Módulo único de datas do Rito (spec 040, alvo 1) — puro: sem banco, sem relógio,
sem framework. Cada função recebe tudo de que precisa por parâmetro.

Aqui moram as lógicas de calendário que nasceram separadas:

- **dias úteis e feriados** (spec 038 — workflows);
- **próxima ocorrência de recorrência** (spec 034 — séries de tarefas), com os enums
  `RecurrencePeriod`/`RecurrenceWeek` (os valores persistidos no PG enum mudam nunca —
  só a casa da classe Python mudou; `app/domain/posts/models.py` re-exporta);
- **aritmética de mês** (fim de mês, início do mês seguinte/anterior, n-ésima e última
  semana do mês) — antes duplicada em lawsuits/stats.py e taskscore/repository.py;
- **prazo processual** (spec 126 — arts. 219, 220 e 224 do CPC): a cadeia
  disponibilização → publicação → dia 1 → vencimento, em dias úteis ou corridos.

Specs futuras DEVEM usar daqui em vez de recriar: 057 (parcelamento financeiro) usa
`add_business_days`/aritmética de mês; 086 e 126 (prazo de intimação) usam
`procedural_deadline`.
"""

from calendar import monthrange
from collections.abc import Callable, Collection, Iterator
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


def _clamp_day(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, monthrange(year, month)[1]))


def card_cycle_range(cycle_day: int, today: date) -> tuple[date, date]:
    """Ciclo de fatura do cartão (spec 055, regra 5): do dia `cycle_day` até o dia
    anterior do mesmo dia no mês seguinte — dia 31 num mês curto usa o último dia
    (mesmo clamp de `next_occurrence`/DIA_EXATO)."""
    start_this_month = _clamp_day(today.year, today.month, cycle_day)
    if today >= start_this_month:
        start = start_this_month
    else:
        prev_year, prev_month = shift_month(today.year, today.month, -1)
        start = _clamp_day(prev_year, prev_month, cycle_day)
    next_year, next_month = shift_month(start.year, start.month, 1)
    end = _clamp_day(next_year, next_month, cycle_day) - timedelta(days=1)
    return start, end


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


def _advance(start: date, offset: int, counts: Callable[[date], bool]) -> date:
    """O laço compartilhado por `add_business_days` e `add_procedural_days`: anda um dia
    de cada vez e só conta os dias em que `counts` responde `True`.

    Existe como função porque as duas variantes diferem SÓ no predicado — e escrever o
    mesmo `while` duas vezes é como um dos dois envelhece sem o outro.
    """
    if offset < 0:
        raise ValueError("days_offset não pode ser negativo.")
    if offset == 0:
        return start
    current = start
    counted = 0
    while counted < offset:
        current += timedelta(days=1)
        if counts(current):
            counted += 1
    return current


def add_business_days(start: date, offset: int, holidays: Collection[date]) -> date:
    """Avança `offset` dias úteis a partir de `start`.

    Regra 4: offset 0 é o próprio dia do disparo, mesmo que caia em fim de semana ou
    feriado — "hoje" não desliza. Offset N ≥ 1 devolve o N-ésimo dia útil seguinte.
    """
    return _advance(start, offset, lambda day: is_business_day(day, holidays))


# ---------------------------------------------------------------------------
# Prazo processual (spec 126 — CPC arts. 219, 220 e 224)
#
# Só a MECÂNICA mora aqui, e ela é lei, não estimativa: quando o prazo começa a correr,
# quais dias contam e quando ele vence. QUANTOS dias cada intimação dá (15 para
# contestar, 5 para embargar, 30 para a Fazenda…) não é assunto deste módulo nem deste
# projeto — não existe tabela de prazos por classe/assunto do CNJ aqui, e inventar uma
# seria pior do que não ter, porque prazo preenchido é prazo em que se confia. Quem
# informa o número é quem responde por ele: o texto da intimação (spec 086) ou a
# configuração do escritório (spec 126).
# ---------------------------------------------------------------------------

# Art. 220: "Suspende-se o curso do prazo processual nos dias compreendidos entre 20 de
# dezembro e 20 de janeiro, inclusive." As duas pontas entram.
COURT_RECESS_START = (12, 20)
COURT_RECESS_END = (1, 20)


def is_court_recess(day: date) -> bool:
    """O dia cai no recesso forense do art. 220 do CPC (20/12 a 20/01, inclusive)."""
    if day.month == COURT_RECESS_START[0]:
        return day.day >= COURT_RECESS_START[1]
    if day.month == COURT_RECESS_END[0]:
        return day.day <= COURT_RECESS_END[1]
    return False


def is_procedural_day(day: date, holidays: Collection[date], *, court_recess: bool = True) -> bool:
    """O dia em que o prazo processual CORRE: dia útil (art. 219) e fora do recesso.

    A diferença entre "não é dia útil" e "está no recesso" é de natureza — o feriado não
    conta porque não há expediente, o recesso não conta porque a lei suspende o curso —,
    mas o efeito sobre a contagem é o mesmo, e é por isso que cabem no mesmo predicado.
    """
    return is_business_day(day, holidays) and not (court_recess and is_court_recess(day))


def add_procedural_days(
    start: date, offset: int, holidays: Collection[date], *, court_recess: bool = True
) -> date:
    """Avança `offset` dias de prazo processual a partir de `start` (exclusivo).

    `start` é o dia do começo, que o art. 224 manda EXCLUIR — por isso a contagem parte
    do dia seguinte, e offset 1 já é o primeiro dia do prazo.
    """
    return _advance(
        start, offset, lambda day: is_procedural_day(day, holidays, court_recess=court_recess)
    )


def publication_date(availability_date: date, holidays: Collection[date]) -> date:
    """A data da PUBLICAÇÃO a partir da data da DISPONIBILIZAÇÃO no diário eletrônico.

    CPC art. 224 §2 (e Lei 11.419/2006 art. 4º §3º): "considera-se como data da
    publicação o primeiro dia útil seguinte ao da disponibilização". São duas datas
    diferentes, e é o erro mais fácil de cometer aqui — o DJEN entrega
    `data_disponibilizacao`, e tratá-la como publicação encurta todo prazo em um dia
    útil.
    """
    return add_business_days(availability_date, 1, holidays)


def procedural_deadline(
    availability_date: date,
    days: int,
    holidays: Collection[date],
    *,
    count_in_business_days: bool = True,
    court_recess: bool = True,
) -> date:
    """O vencimento de um prazo de `days` dias contado da disponibilização.

    A cadeia inteira do CPC, em três passos:

    1. **art. 224 §2** — disponibilização → publicação é o primeiro dia útil seguinte;
    2. **art. 224 caput/§3** — exclui-se o dia do começo (a publicação): o dia 1 é o
       primeiro dia em que o prazo corre depois dela;
    3. **art. 219** — em dias úteis, e **art. 220** — sem os dias do recesso.

    `count_in_business_days=False` é o prazo em dias corridos (art. 219, parágrafo
    único: a contagem em dias úteis vale só para prazo processual). Aí o recesso não
    suspende nada e o único ajuste é o do **art. 224 §1**: vencimento em dia sem
    expediente prorroga para o dia útil seguinte.
    """
    if days < 1:
        raise ValueError("Prazo em dias precisa ser ao menos 1.")
    published = publication_date(availability_date, holidays)
    if count_in_business_days:
        return add_procedural_days(published, days, holidays, court_recess=court_recess)
    due = published + timedelta(days=days)
    while not is_business_day(due, holidays):
        due += timedelta(days=1)
    return due


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
