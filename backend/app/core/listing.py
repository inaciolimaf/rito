"""Infra de listagem (spec 030, alvo 2): keyset, intervalos de data e visões rápidas
declarativas — extraído das listagens de contatos (019) e processos (027), que repetiam
as três estruturas. Tarefas (036) e financeiro (054+) consomem daqui.

Regras do contrato de listagem (CLAUDE.md §6) que este módulo ancora:
- keyset, nunca offset — o cursor é `(valor_da_ordenação, id)` comparado como tupla;
- filtros combinam com AND entre grupos e OR (IN) dentro de um grupo multivalorado.
"""

import uuid
from collections.abc import Callable, Mapping
from datetime import date, datetime, time
from typing import Any

from sqlalchemy import ColumnElement, DateTime, Select, literal, tuple_
from sqlalchemy.orm import InstrumentedAttribute

Predicate = ColumnElement[bool]
Column = InstrumentedAttribute[Any] | ColumnElement[Any]


def datetime_range(column: Column, start: date | None, end: date | None) -> list[Predicate]:
    """Intervalo sobre coluna `timestamp` — de 00:00 do dia inicial a 23:59:59 do final.

    Um lado só é válido (intervalo aberto): `created_from` sem `created_to` filtra "a
    partir de". Unifica o padrão de contatos (019) e processos (027, `created_*`)."""
    conditions: list[Predicate] = []
    if start is not None:
        conditions.append(column >= datetime.combine(start, time.min))
    if end is not None:
        conditions.append(column <= datetime.combine(end, time.max))
    return conditions


def date_range(column: Column, start: date | None, end: date | None) -> list[Predicate]:
    """Intervalo sobre coluna `date` — comparação direta, sem combine (027: `process_*`,
    `closure_*`, `transit_*`, `archived_*`)."""
    conditions: list[Predicate] = []
    if start is not None:
        conditions.append(column >= start)
    if end is not None:
        conditions.append(column <= end)
    return conditions


def paginate_keyset[StmtT: Select[Any]](
    stmt: StmtT,
    *,
    sort_column: Column,
    id_column: InstrumentedAttribute[uuid.UUID],
    descending: bool,
    cursor: tuple[Any, uuid.UUID] | None,
    limit: int,
) -> StmtT:
    """Ordena por (sort, id) e aplica o predicado keyset do cursor.

    O par `(sort, id)` é comparado como TUPLA — desempate estável mesmo com valores de
    ordenação repetidos (created_at no mesmo segundo). `cursor=None` é a primeira
    página; a contagem total fica a cargo do chamador (query separada, sem o predicado
    do cursor)."""
    order_column = sort_column.desc() if descending else sort_column.asc()
    secondary = id_column.desc() if descending else id_column.asc()
    stmt = stmt.order_by(order_column, secondary).limit(limit)
    if cursor is not None:
        cursor_value, cursor_id = cursor
        # O cursor viaja como texto (base64 de `valor|id`), então o valor de uma coluna
        # temporal chega como string ISO. Comparar `timestamptz < varchar` não existe no
        # Postgres — e o erro só apareceria na SEGUNDA página, que é o pior lugar para
        # descobrir. Spec 095.
        if isinstance(sort_column.type, DateTime) and isinstance(cursor_value, str):
            cursor_value = datetime.fromisoformat(cursor_value)
        pair = tuple_(sort_column, id_column)
        cursor_pair = tuple_(literal(cursor_value), literal(cursor_id))
        stmt = stmt.where(pair < cursor_pair if descending else pair > cursor_pair)
    return stmt


class QuickViews:
    """Visões rápidas declarativas: nome → fábrica de predicado.

    Nome desconhecido cai no `default` (a listagem completa) — visão é atalho, nunca
    erro. A fábrica (e não o predicado pronto) é o que se registra porque predicados
    frequentemente dependem de `func.now()` avaliado no momento da query."""

    def __init__(
        self, *, default: str, views: Mapping[str, Callable[[], Predicate | None]]
    ) -> None:
        self.default = default
        self._views = dict(views)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._views)

    def __contains__(self, view: str) -> bool:
        return view in self._views

    def resolve(self, view: str) -> str:
        return view if view in self._views else self.default

    def predicate(self, view: str) -> Predicate | None:
        """None = visão sem predicado (a visão "todos")."""
        return self._views[self.resolve(view)]()
