"""Execução de grafos de agente (spec 082).

O grafo (LangGraph) sabe o caminho; o runtime é quem garante as regras do produto:
checkpoint a cada nó (1), interrupção para o humano (2), limite de 25 passos (9),
timeout por nó e por execução (5), cancelamento na fronteira do nó (6), registro de
todo passo (7) e corte de payload gigante (8).

Nada aqui importa `langgraph` no topo: o import mora no módulo do grafo, carregado sob
demanda pelo registro. Assim o `app.main` (e todo worker de teste) não paga ~2 s de
import de `langchain_core` para servir uma rota que não usa IA.
"""

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.ai.graphs.base import PENDING_ACTION_KEY, GraphDeps, GraphResult, PendingAction
from app.ai.graphs.registry import get_graph
from app.core.rls import set_tenant_context
from app.domain.ai.models import AiCheckpoint, AiStep, AiThread, ThreadStatus

logger = logging.getLogger("rito.ai.runtime")

# Regra 9: teto de passos por execução — a proteção contra laço infinito.
MAX_STEPS = 25
# Regra 5.
NODE_TIMEOUT_S = 300.0
RUN_TIMEOUT_S = 900.0
# Regra 8.
MAX_PAYLOAD_BYTES = 100 * 1024


class NodeTimeoutError(Exception):
    """Nó estourou o tempo (regra 5) — o thread termina em `error`, nunca pendurado."""


class StepLimitError(Exception):
    """Passo 26 (regra 9)."""


class ThreadCancelledError(Exception):
    """Cancelado pelo usuário entre um nó e outro (regra 6)."""


class RuntimeSessionLostError(Exception):
    """A sessão de quem chamou não sobreviveu ao corte do timeout (spec 103, dívida 21).

    Levantada **depois** de o passo de erro já ter sido gravado, por uma conexão
    própria: o que se perdeu foi a transação da requisição, não o registro. Quem chamou
    traduz isto em 503 — e o `rollback` de quem abriu a transação devolve a conexão.
    """


@dataclass(frozen=True)
class StepEvent:
    """Um passo, para quem está assistindo pelo SSE."""

    step: int
    node: str
    kind: str
    output: dict[str, Any] | None
    duration_ms: int


def truncate_payload(payload: Any) -> dict[str, Any] | None:
    """Regra 8: acima de 100 KB, guarda referência em vez do conteúdo.

    Guardar o payload inteiro transformaria `ai_steps` no maior objeto do banco na
    primeira petição gerada — e a auditoria precisa saber o QUE aconteceu, não reler o
    documento inteiro (que está salvo no seu próprio lugar).
    """
    if payload is None:
        return None
    if not isinstance(payload, dict):
        payload = {"value": payload}
    encoded = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    if len(encoded) <= MAX_PAYLOAD_BYTES:
        return dict(payload)
    return {
        "truncated": True,
        "size_bytes": len(encoded),
        "preview": encoded[:512].decode("utf-8", errors="ignore"),
        "keys": sorted(str(key) for key in payload),
    }


class GraphRuntime:
    def __init__(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        deps: GraphDeps | None = None,
        max_steps: int = MAX_STEPS,
        node_timeout_s: float = NODE_TIMEOUT_S,
        run_timeout_s: float = RUN_TIMEOUT_S,
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.deps = deps
        self.max_steps = max_steps
        self.node_timeout_s = node_timeout_s
        self.run_timeout_s = run_timeout_s

    # ------------------------------------------------------------------ API

    async def start(self, thread: AiThread, input_: dict[str, Any]) -> GraphResult:
        state: dict[str, Any] = {"input": input_, "scratch": {}, "messages": []}
        thread.state = state
        return await self._drive(thread, state)

    async def resume(
        self, thread: AiThread, *, approved: bool, human_input: dict[str, Any] | None
    ) -> GraphResult:
        """Regra 3: retomar exige decisão explícita. Recusa encerra o thread como
        `cancelled` com o motivo — o agente não insiste."""
        if not approved:
            return await self._refuse(thread, human_input)
        state = dict(thread.state or {})
        state["approved"] = True
        state["human_input"] = human_input or {}
        # A ação pendente sai do estado: ela já foi decidida, e deixá-la ali faria o
        # runtime achar que o grafo interrompeu de novo no primeiro checkpoint.
        state[PENDING_ACTION_KEY] = None
        thread.pending_action = None
        thread.waiting_since = None
        return await self._drive(thread, state)

    async def stream(
        self, thread: AiThread, *, input_: dict[str, Any] | None = None
    ) -> AsyncIterator[StepEvent | GraphResult]:
        """Mesma execução de `start`, emitindo cada passo — é o que o SSE consome."""
        state: dict[str, Any] = (
            {"input": input_ or {}, "scratch": {}, "messages": []}
            if input_ is not None
            else dict(thread.state or {})
        )
        async for event in self._drive_iter(thread, state):
            yield event

    # -------------------------------------------------------------- interno

    async def _drive(self, thread: AiThread, state: dict[str, Any]) -> GraphResult:
        result: GraphResult | None = None
        async for event in self._drive_iter(thread, state):
            if isinstance(event, GraphResult):
                result = event
        assert result is not None  # _drive_iter sempre encerra com um GraphResult
        return result

    async def _preparar_execucao(
        self, thread: AiThread, state: dict[str, Any]
    ) -> tuple[AsyncIterator[dict[str, Any]], float]:
        """Monta o grafo, marca o thread como RUNNING e devolve o iterador e o prazo.

        Extraído de `_drive_iter` (spec 106): é prelúdio, acontece uma vez, e estava
        misturado com o laço que roda N vezes. `self.deps` só é `None` fora dos testes —
        em produção o runner monta as dependências antes de chegar aqui.
        """
        graph = get_graph(thread.graph_name)
        deps = self.deps or GraphDeps(
            tenant_id=self.tenant_id,
            user_id=thread.user_id,
            llm=None,
            feature_key=thread.feature_key,
            context=dict(thread.context or {}),
        )
        compiled = graph.build(deps)
        thread.status = ThreadStatus.RUNNING.value
        await self.session.flush()
        return (
            compiled.astream(state, stream_mode="updates").__aiter__(),
            time.monotonic() + self.run_timeout_s,
        )

    async def _drive_iter(
        self, thread: AiThread, state: dict[str, Any]
    ) -> AsyncIterator[StepEvent | GraphResult]:
        iterator, deadline = await self._preparar_execucao(thread, state)

        while True:
            started = time.monotonic()
            try:
                # Regra 6: a checagem de cancelamento é ENTRE nós — nunca no meio de um
                # nó, que poderia estar com uma escrita em andamento.
                await self._ensure_not_cancelled(thread)
                if time.monotonic() > deadline:
                    raise NodeTimeoutError("execução excedeu o tempo total")
                update = await asyncio.wait_for(iterator.__anext__(), timeout=self.node_timeout_s)
            except StopAsyncIteration:
                break
            except TimeoutError as exc:
                yield await self._fail(
                    thread, state, "timeout", f"nó excedeu {self.node_timeout_s:.0f}s", exc
                )
                return
            except NodeTimeoutError as exc:
                yield await self._fail(thread, state, "timeout", str(exc), exc)
                return
            except ThreadCancelledError:
                yield GraphResult(status="error", error="Execução cancelada.")
                return
            except Exception as exc:  # regra 10: erro de nó nunca é silencioso
                yield await self._fail(thread, state, "erro", str(exc), exc)
                return

            duration_ms = int((time.monotonic() - started) * 1000)
            async for novo_state, evento in self._passos_do_update(
                thread, state, update, duration_ms
            ):
                state = novo_state
                yield evento
                # `GraphResult` no meio do laço é sempre um desfecho — limite de passos
                # estourado ou interrupção esperando confirmação humana.
                if isinstance(evento, GraphResult):
                    return

        yield await self._finish(thread, state)

    async def _passos_do_update(
        self,
        thread: AiThread,
        state: dict[str, Any],
        update: dict[str, Any],
        duration_ms: int,
    ) -> AsyncIterator[tuple[dict[str, Any], StepEvent | GraphResult]]:
        """Um update do grafo pode trazer vários nós; este gerador emite um evento por nó.

        Extraído de `_drive_iter` na spec 106. Devolve o estado junto com o evento porque
        cada nó reescreve o estado, e quem itera precisa do valor novo para o próximo —
        um gerador não tem como devolver valor de retorno e continuar rendendo.
        """
        for node, delta in update.items():
            state = {**state, **(delta or {})}
            thread.step_count += 1
            if thread.step_count > self.max_steps:
                yield state, await self._fail(
                    thread,
                    state,
                    "limite",
                    f"execução passou de {self.max_steps} passos",
                    StepLimitError(),
                    count_step=False,
                )
                return
            kind = "interrupt" if state.get(PENDING_ACTION_KEY) else "node"
            await self._record_step(
                thread,
                node=str(node),
                kind=kind,
                output=delta,
                duration_ms=duration_ms,
                state=state,
            )
            yield state, StepEvent(
                step=thread.step_count,
                node=str(node),
                kind=kind,
                output=truncate_payload(delta),
                duration_ms=duration_ms,
            )
            if state.get(PENDING_ACTION_KEY):
                yield state, await self._interrupt(thread, state)
                return

    async def _ensure_not_cancelled(self, thread: AiThread) -> None:
        """Cancelamento vem de OUTRA request, então o valor em memória não serve — a
        checagem lê o status corrente do banco."""
        await self.session.refresh(thread, ["status"])
        if thread.status == ThreadStatus.CANCELLED.value:
            raise ThreadCancelledError

    async def _record_step(
        self,
        thread: AiThread,
        *,
        node: str,
        kind: str,
        output: dict[str, Any] | None,
        duration_ms: int,
        state: dict[str, Any],
        error: str | None = None,
    ) -> None:
        self.session.add(
            AiStep(
                tenant_id=self.tenant_id,
                thread_id=thread.id,
                step=thread.step_count,
                node=node,
                kind=kind,
                input=truncate_payload(state.get("input")),
                output=truncate_payload(output),
                duration_ms=duration_ms,
                error=error,
            )
        )
        # Regra 1: o checkpoint é o estado DEPOIS do nó — é dele que a retomada parte.
        self.session.add(
            AiCheckpoint(
                tenant_id=self.tenant_id,
                thread_id=thread.id,
                step=thread.step_count,
                node=node,
                state=truncate_payload(state) or {},
            )
        )
        thread.state = state
        await self.session.flush()

    async def _interrupt(self, thread: AiThread, state: dict[str, Any]) -> GraphResult:
        pending = state.get(PENDING_ACTION_KEY)
        thread.status = ThreadStatus.WAITING_HUMAN.value
        thread.pending_action = pending
        thread.waiting_since = datetime.now(UTC)
        thread.state = state
        await self.session.flush()
        return GraphResult(status="waiting_human", pending_action=pending)

    async def _finish(self, thread: AiThread, state: dict[str, Any]) -> GraphResult:
        output = state.get("output")
        thread.status = ThreadStatus.DONE.value
        thread.output = output
        thread.state = state
        thread.finished_at = datetime.now(UTC)
        await self.session.flush()
        return GraphResult(status="done", output=output)

    async def _fail(
        self,
        thread: AiThread,
        state: dict[str, Any],
        node: str,
        message: str,
        exc: BaseException,
        count_step: bool = True,
    ) -> GraphResult:
        logger.warning("Grafo %s falhou em %s: %s", thread.graph_name, node, message)
        if count_step:
            # No estouro de passos o contador já subiu ao tentar o passo proibido —
            # contar de novo faria o thread parecer ter dado um passo a mais do que deu.
            thread.step_count += 1
        thread.status = ThreadStatus.ERROR.value
        thread.error = message
        thread.finished_at = datetime.now(UTC)
        thread.state = state
        # Lidos ANTES da escrita: uma escrita que falha expira o objeto, e a partir daí
        # ler `thread.id` dispara um carregamento preguiçoso na sessão que já morreu.
        thread_id, step = thread.id, thread.step_count
        try:
            await self._record_step(
                thread,
                node=node,
                kind="error",
                output=None,
                duration_ms=0,
                state=state,
                error=message,
            )
        except SQLAlchemyError as write_error:
            # Spec 103: a sessão de quem chamou pode estar morta JUSTAMENTE por causa
            # da falha que se está tentando registrar — o `wait_for` do timeout corta
            # onde a corrotina estiver, e cortar uma query em voo invalida a CONEXÃO,
            # não só a transação. O registro então vai por uma conexão própria, e a
            # requisição morre em 503 em vez de morrer calada.
            await self._record_failure_out_of_band(
                thread_id, step, node=node, message=message, state=state
            )
            raise RuntimeSessionLostError(message) from write_error
        del exc
        return GraphResult(status="error", error=message)

    async def _record_failure_out_of_band(
        self,
        thread_id: uuid.UUID,
        step: int,
        *,
        node: str,
        message: str,
        state: dict[str, Any],
    ) -> None:
        """O passo de erro numa sessão que o runtime abre, usa e fecha.

        Não é o caminho normal — é o caminho de quando o normal não existe mais. Por
        isso escreve por `update()` em vez de mexer no objeto `thread`, que pertence à
        sessão morta, e commita sozinho: o registro da falha não pode depender do
        commit de uma transação que já não vai acontecer.

        Só alcança thread **já comitado** — linha não comitada não existe para outra
        conexão. É por isso que quem cria e roda no mesmo request cria de forma durável
        antes (`create_durable_thread`, `app/domain/ai/threads.py`).
        """
        bind = self.session.bind
        if not isinstance(bind, AsyncEngine):  # pragma: no cover — só em teste com bind exótico
            logger.error("Sem engine para registrar a falha fora de banda: %s", message)
            return
        snapshot = truncate_payload(state) or {}
        try:
            async with AsyncSession(bind) as book, book.begin():
                await set_tenant_context(book, self.tenant_id)
                book.add(
                    AiStep(
                        tenant_id=self.tenant_id,
                        thread_id=thread_id,
                        step=step,
                        node=node,
                        kind="error",
                        input=truncate_payload(state.get("input")),
                        output=None,
                        duration_ms=0,
                        error=message,
                    )
                )
                book.add(
                    AiCheckpoint(
                        tenant_id=self.tenant_id,
                        thread_id=thread_id,
                        step=step,
                        node=node,
                        state=snapshot,
                    )
                )
                await book.execute(
                    update(AiThread)
                    .where(AiThread.id == thread_id)
                    .values(
                        status=ThreadStatus.ERROR.value,
                        error=message,
                        finished_at=datetime.now(UTC),
                        step_count=step,
                        state=snapshot,
                        pending_action=None,
                        waiting_since=None,
                    )
                )
        except SQLAlchemyError:
            # Registrar a falha falhou. Não há terceira sessão para tentar de novo — o
            # que sobra é o log, alto, com o motivo original junto.
            logger.exception("Falha ao registrar fora de banda o erro do thread %s", thread_id)

    async def _refuse(self, thread: AiThread, human_input: dict[str, Any] | None) -> GraphResult:
        reason = (human_input or {}).get("reason") or "Recusado pelo usuário."
        thread.step_count += 1
        await self._record_step(
            thread,
            node="human",
            kind="interrupt",
            output={"approved": False, "reason": reason},
            duration_ms=0,
            state=dict(thread.state or {}),
        )
        thread.status = ThreadStatus.CANCELLED.value
        thread.error = str(reason)
        thread.pending_action = None
        thread.waiting_since = None
        thread.finished_at = datetime.now(UTC)
        await self.session.flush()
        return GraphResult(status="error", error=str(reason))


__all__ = [
    "MAX_PAYLOAD_BYTES",
    "MAX_STEPS",
    "NODE_TIMEOUT_S",
    "RUN_TIMEOUT_S",
    "GraphResult",
    "GraphRuntime",
    "NodeTimeoutError",
    "PendingAction",
    "RuntimeSessionLostError",
    "StepEvent",
    "StepLimitError",
    "ThreadCancelledError",
    "truncate_payload",
]
