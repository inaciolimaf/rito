"""Cola entre os sinais do Celery e a propagação de contexto (spec 097, regras 2 e 5).

Este módulo é a única parte da observabilidade que sabe que existe Celery. A lógica
mora em `app/core/observability/propagation.py`, sem dependência de fila — aqui só se
liga um sinal a uma função.

`before_task_publish` roda no processo de QUEM enfileira (a requisição HTTP), que é o
único lugar onde o `request_id` e o `traceparent` do clique existem. `task_prerun` roda
no worker, do outro lado do Redis, e é onde eles voltam a valer.
"""

import logging
from typing import Any

from celery.signals import before_task_publish, task_failure, task_postrun, task_prerun

from app.core.observability.propagation import (
    TaskScope,
    bind_task_headers,
    build_task_headers,
    release_task_scope,
)

logger = logging.getLogger("rito.worker")

# Escopo por id de task: o worker de prefork executa uma task por vez no processo
# filho, mas o de threads/gevent não — a chave por id mantém os dois corretos.
_scopes: dict[str, TaskScope] = {}


@before_task_publish.connect
def _inject(headers: dict[str, Any] | None = None, **_: Any) -> None:
    if headers is None:
        return
    # No protocolo v2 do Celery, `headers` É o dicionário de headers da mensagem: o
    # que se põe aqui chega ao worker em `task.request`.
    headers.update(build_task_headers())


@task_prerun.connect
def _bind(task_id: str | None = None, task: Any = None, **_: Any) -> None:
    if task_id is None or task is None:
        return
    entregues = getattr(task.request, "__dict__", {}) or {}
    headers = {chave: valor for chave, valor in entregues.items() if isinstance(valor, str)}
    _scopes[task_id] = bind_task_headers(headers, task_name=task.name)


@task_failure.connect
def _mark_failure(
    task_id: str | None = None, exception: BaseException | None = None, **_: Any
) -> None:
    scope = _scopes.get(task_id or "")
    if scope is not None and exception is not None:
        scope.span.record_exception(exception)


@task_postrun.connect
def _release(task_id: str | None = None, **_: Any) -> None:
    scope = _scopes.pop(task_id or "", None)
    if scope is not None:
        release_task_scope(scope)
