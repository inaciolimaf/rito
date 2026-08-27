"""Contexto de correlação — o que amarra log, métrica e trace da mesma ação.

Tudo aqui é `ContextVar`: o valor viaja com a task asyncio que atende a requisição,
sem precisar ser passado de parâmetro em parâmetro até o fundo do service. É o mesmo
mecanismo que o `request_id` já usava desde a 002; a 097 só o estende para os outros
campos que a regra 1 exige no log.
"""

import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
tenant_id_var: ContextVar[str | None] = ContextVar("tenant_id", default=None)
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)
route_var: ContextVar[str | None] = ContextVar("route", default=None)


@dataclass
class QueryCounter:
    """Contador MUTÁVEL de queries da requisição corrente.

    O contexto guarda o objeto, não o número, e o listener do SQLAlchemy incrementa o
    atributo. A diferença importa: o SQLAlchemy async executa o driver dentro de um
    greenlet, que tem contexto próprio — um `ContextVar.set(n+1)` lá dentro morreria no
    greenlet e o contador chegaria zerado ao middleware. Mutar um objeto compartilhado
    é visível de qualquer contexto que enxergue a mesma referência.
    """

    count: int = 0


query_counter_var: ContextVar[QueryCounter | None] = ContextVar("query_counter", default=None)


def start_query_counter() -> Token[QueryCounter | None]:
    return query_counter_var.set(QueryCounter())


def current_query_count() -> int:
    counter = query_counter_var.get()
    return counter.count if counter is not None else 0


def count_query() -> None:
    counter = query_counter_var.get()
    if counter is not None:
        counter.count += 1


@dataclass(frozen=True)
class CorrelationSnapshot:
    """Foto do contexto para atravessar uma fronteira (fila, thread, processo)."""

    request_id: str | None
    tenant_id: str | None
    user_id: str | None


def new_request_id() -> str:
    return str(uuid.uuid4())


def current_correlation() -> CorrelationSnapshot:
    return CorrelationSnapshot(
        request_id=request_id_var.get(),
        tenant_id=tenant_id_var.get(),
        user_id=user_id_var.get(),
    )


def bind_correlation(snapshot: CorrelationSnapshot) -> list[Token[str | None]]:
    """Aplica um snapshot ao contexto corrente e devolve os tokens para desfazer.

    Devolver os tokens (em vez de um contextmanager) é o que permite ao worker do
    Celery ligar o contexto no `task_prerun` e desligar no `task_postrun` — dois
    callbacks separados, sem um `with` capaz de abraçar os dois.
    """
    return [
        request_id_var.set(snapshot.request_id),
        tenant_id_var.set(snapshot.tenant_id),
        user_id_var.set(snapshot.user_id),
    ]


def reset_correlation(tokens: list[Token[str | None]]) -> None:
    for var, token in zip((request_id_var, tenant_id_var, user_id_var), tokens, strict=True):
        var.reset(token)
