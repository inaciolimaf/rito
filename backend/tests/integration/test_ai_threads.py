"""Runtime de agentes (spec 082) — grafos determinísticos, LLM nunca chamado.

Cada grafo de teste é um grafo LangGraph de verdade (é o runtime real que está sob
teste), mas os nós são funções determinísticas: o que se verifica aqui é o
comportamento do RUNTIME — checkpoint, interrupção, retomada, limite, timeout,
cancelamento e auditoria —, não o que um modelo responderia.
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from langgraph.graph import END, StateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.graphs.base import GraphDeps, GraphState, PendingAction, interrupt_for
from app.ai.graphs.registry import register_graph
from app.ai.runtime import GraphRuntime
from app.core.rls import set_tenant_context
from app.domain.ai.models import AiCheckpoint, AiStep, AiThread, ThreadStatus
from app.domain.ai.threads import AiThreadService
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser, auth_header

# ------------------------------------------------------------------ grafos de teste


class _Graph:
    """Grafo mínimo: nome, feature e um builder que o teste fornece."""

    def __init__(self, name: str, builder: Callable[[GraphDeps], Any]) -> None:
        self.name = name
        self.feature_key = "copilot"
        self._builder = builder

    def build(self, deps: GraphDeps) -> Any:
        return self._builder(deps)


def _two_steps(_deps: GraphDeps) -> Any:
    """coleta → responde. O roteador de entrada é o que torna o grafo retomável."""
    graph = StateGraph(GraphState)

    async def collect(state: GraphState) -> dict[str, Any]:
        return {"scratch": {**(state.get("scratch") or {}), "collected": True}}

    async def answer(state: GraphState) -> dict[str, Any]:
        return {"output": {"answer": (state.get("input") or {}).get("question", "").upper()}}

    def route(state: GraphState) -> str:
        if state.get("output") is not None:
            return END
        if (state.get("scratch") or {}).get("collected"):
            return "answer"
        return "collect"

    graph.add_node("collect", collect)
    graph.add_node("answer", answer)
    graph.set_conditional_entry_point(route, {"collect": "collect", "answer": "answer", END: END})
    graph.add_edge("collect", "answer")
    graph.add_edge("answer", END)
    return graph.compile()


def _with_interrupt(_deps: GraphDeps) -> Any:
    """propõe → (humano) → aplica. É o padrão de toda escrita feita por IA (084)."""
    graph = StateGraph(GraphState)

    async def propose(state: GraphState) -> dict[str, Any]:
        return interrupt_for(
            PendingAction(
                kind="create_task",
                title="Criar tarefa de contestação",
                preview={"prazo": "15 dias"},
            )
        )

    async def apply(state: GraphState) -> dict[str, Any]:
        return {
            "output": {
                "created": True,
                "note": (state.get("human_input") or {}).get("note"),
            }
        }

    def route(state: GraphState) -> str:
        if state.get("output") is not None:
            return END
        if state.get("approved"):
            return "apply"
        return "propose"

    graph.add_node("propose", propose)
    graph.add_node("apply", apply)
    graph.set_conditional_entry_point(route, {"propose": "propose", "apply": "apply", END: END})
    graph.add_edge("propose", END)
    graph.add_edge("apply", END)
    return graph.compile()


_FAILURES: dict[str, int] = {}


async def _no_caro(state: GraphState) -> dict[str, Any]:
    _FAILURES["expensive_runs"] = _FAILURES.get("expensive_runs", 0) + 1
    return {"scratch": {**(state.get("scratch") or {}), "expensive_done": True}}


async def _no_fragil(state: GraphState) -> dict[str, Any]:
    """Falha na PRIMEIRA execução e só na primeira — é o que torna a retomada
    observável: se o grafo repetisse o nó caro, o contador denunciaria."""
    _FAILURES["fragile_runs"] = _FAILURES.get("fragile_runs", 0) + 1
    if _FAILURES["fragile_runs"] == 1:
        raise RuntimeError("falha transitória do nó")
    return {"output": {"ok": True}}


def _rota_caro_fragil(state: GraphState) -> str:
    if state.get("output") is not None:
        return END
    return "fragile" if (state.get("scratch") or {}).get("expensive_done") else "expensive"


def _fails_once(_deps: GraphDeps) -> Any:
    """caro → frágil. O nó `caro` só pode rodar UMA vez: se a retomada o repetisse, o
    contador denunciaria."""
    graph = StateGraph(GraphState)
    graph.add_node("expensive", _no_caro)
    graph.add_node("fragile", _no_fragil)
    graph.set_conditional_entry_point(
        _rota_caro_fragil, {"expensive": "expensive", "fragile": "fragile", END: END}
    )
    graph.add_edge("expensive", "fragile")
    graph.add_edge("fragile", END)
    return graph.compile()


def _endless(_deps: GraphDeps) -> Any:
    """Laço que nunca converge — o teto de passos (regra 9) é a única saída."""
    graph = StateGraph(GraphState)

    async def tick(state: GraphState) -> dict[str, Any]:
        scratch = dict(state.get("scratch") or {})
        scratch["ticks"] = int(scratch.get("ticks", 0)) + 1
        return {"scratch": scratch}

    graph.add_node("tick", tick)
    graph.set_entry_point("tick")
    graph.add_edge("tick", "tick")
    return graph.compile()


def _hangs(_deps: GraphDeps) -> Any:
    """Nó que nunca termina — espera um evento que ninguém dispara (sem `sleep`)."""
    graph = StateGraph(GraphState)

    async def hang(state: GraphState) -> dict[str, Any]:
        await asyncio.Event().wait()
        return dict(state)

    graph.add_node("hang", hang)
    graph.set_entry_point("hang")
    graph.add_edge("hang", END)
    return graph.compile()


def _huge(_deps: GraphDeps) -> Any:
    """Saída de 200 KB — acima do teto da regra 8."""
    graph = StateGraph(GraphState)

    async def big(state: GraphState) -> dict[str, Any]:
        del state
        return {"output": {"documento": "x" * 200_000}}

    graph.add_node("big", big)
    graph.set_entry_point("big")
    graph.add_edge("big", END)
    return graph.compile()


@pytest.fixture(autouse=True)
def _register_test_graphs() -> None:
    for name, builder in (
        ("test_two_steps", _two_steps),
        ("test_interrupt", _with_interrupt),
        ("test_fails_once", _fails_once),
        ("test_endless", _endless),
        ("test_hangs", _hangs),
        ("test_huge", _huge),
    ):
        register_graph(_Graph(name, builder))


# ------------------------------------------------------------------ helpers


async def _new_thread(
    session_factory: async_sessionmaker[AsyncSession],
    user: SeededUser,
    graph_name: str,
) -> uuid.UUID:
    async with session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        service = AiThreadService(session=session, tenant_id=user.tenant_id)
        thread = AiThread(
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            graph_name=graph_name,
            feature_key="copilot",
            status=ThreadStatus.PENDING.value,
        )
        session.add(thread)
        await session.flush()
        del service
        return thread.id


async def _run(
    session_factory: async_sessionmaker[AsyncSession],
    user: SeededUser,
    thread_id: uuid.UUID,
    input_: dict[str, Any] | None = None,
    **runtime_kwargs: Any,
) -> Any:
    async with session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        thread = await session.get(AiThread, thread_id)
        assert thread is not None
        runtime = GraphRuntime(session, user.tenant_id, **runtime_kwargs)
        return await runtime.start(thread, input_ or {})


async def _reload(
    session_factory: async_sessionmaker[AsyncSession], user: SeededUser, thread_id: uuid.UUID
) -> AiThread:
    async with session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        thread = await session.get(AiThread, thread_id)
        assert thread is not None
        await session.refresh(thread)
        return thread


async def _steps(
    session_factory: async_sessionmaker[AsyncSession], user: SeededUser, thread_id: uuid.UUID
) -> list[AiStep]:
    async with session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        stmt = select(AiStep).where(AiStep.thread_id == thread_id).order_by(AiStep.step)
        return list((await session.scalars(stmt)).all())


# ------------------------------------------------------------------ testes


async def test_grafo_simples_executa_e_termina(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await make_user()
    thread_id = await _new_thread(app_session_factory, user, "test_two_steps")

    result = await _run(app_session_factory, user, thread_id, {"question": "quanto falta?"})

    assert result.status == "done"
    assert result.output == {"answer": "QUANTO FALTA?"}
    thread = await _reload(app_session_factory, user, thread_id)
    assert thread.status == ThreadStatus.DONE.value
    # Regra 1: um checkpoint por nó — os dois nós executados.
    steps = await _steps(app_session_factory, user, thread_id)
    assert [step.node for step in steps] == ["collect", "answer"]


async def test_interrompe_persiste_e_retoma_depois_da_aprovacao(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 2 e 3 — o teste que a spec chama de essencial."""
    user = await make_user()
    thread_id = await _new_thread(app_session_factory, user, "test_interrupt")

    parada = await _run(app_session_factory, user, thread_id)

    assert parada.status == "waiting_human"
    assert parada.pending_action is not None
    assert parada.pending_action["kind"] == "create_task"
    esperando = await _reload(app_session_factory, user, thread_id)
    assert esperando.status == ThreadStatus.WAITING_HUMAN.value
    assert esperando.waiting_since is not None
    # O estado tem que estar persistido: é dele que a retomada parte.
    assert esperando.state.get("pending_action") is not None

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        thread = await session.get(AiThread, thread_id)
        assert thread is not None
        runtime = GraphRuntime(session, user.tenant_id)
        retomada = await runtime.resume(thread, approved=True, human_input={"note": "pode criar"})

    assert retomada.status == "done"
    assert retomada.output == {"created": True, "note": "pode criar"}
    final = await _reload(app_session_factory, user, thread_id)
    assert final.status == ThreadStatus.DONE.value
    assert final.pending_action is None


async def test_recusa_encerra_como_cancelado_com_motivo(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 3: recusar não é 'tenta de novo' — encerra, e o motivo fica registrado."""
    user = await make_user()
    thread_id = await _new_thread(app_session_factory, user, "test_interrupt")
    await _run(app_session_factory, user, thread_id)

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        thread = await session.get(AiThread, thread_id)
        assert thread is not None
        runtime = GraphRuntime(session, user.tenant_id)
        await runtime.resume(
            thread, approved=False, human_input={"reason": "prazo já foi cumprido"}
        )

    final = await _reload(app_session_factory, user, thread_id)
    assert final.status == ThreadStatus.CANCELLED.value
    assert final.error == "prazo já foi cumprido"
    steps = await _steps(app_session_factory, user, thread_id)
    assert steps[-1].output == {"approved": False, "reason": "prazo já foi cumprido"}


async def test_falha_no_meio_retoma_do_ultimo_checkpoint(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 1: o nó caro não roda duas vezes — é o ponto inteiro do checkpoint."""
    _FAILURES.clear()
    user = await make_user()
    thread_id = await _new_thread(app_session_factory, user, "test_fails_once")

    primeira = await _run(app_session_factory, user, thread_id)
    assert primeira.status == "error"
    assert _FAILURES["expensive_runs"] == 1

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        thread = await session.get(AiThread, thread_id)
        assert thread is not None
        runtime = GraphRuntime(session, user.tenant_id)
        segunda = await runtime.resume(thread, approved=True, human_input=None)

    assert segunda.status == "done"
    assert _FAILURES["expensive_runs"] == 1, "retomada não pode repetir o nó caro"
    assert _FAILURES["fragile_runs"] == 2


async def test_expira_depois_de_24h_esperando(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 4 — sem `sleep`: o relógio é injetado."""
    user = await make_user()
    thread_id = await _new_thread(app_session_factory, user, "test_interrupt")
    await _run(app_session_factory, user, thread_id)

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        service = AiThreadService(session=session, tenant_id=user.tenant_id)
        expirados = await service.expire_waiting(now=datetime.now(UTC) + timedelta(hours=25))

    assert expirados == 1
    final = await _reload(app_session_factory, user, thread_id)
    assert final.status == ThreadStatus.CANCELLED.value
    assert final.error is not None and "Expirou" in final.error


async def test_timeout_de_no_interrompe_a_execucao(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 5: nó pendurado vira thread em erro, nunca thread eternamente `running`."""
    user = await make_user()
    thread_id = await _new_thread(app_session_factory, user, "test_hangs")

    result = await _run(app_session_factory, user, thread_id, {}, node_timeout_s=0.05)

    assert result.status == "error"
    assert "excedeu" in (result.error or "")
    final = await _reload(app_session_factory, user, thread_id)
    assert final.status == ThreadStatus.ERROR.value
    assert final.finished_at is not None


async def test_cancelamento_respeita_a_fronteira_do_no(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 6: o cancelamento chega no intervalo entre dois nós; o nó em andamento
    termina. O segundo nó nunca começa."""
    user = await make_user()
    thread_id = await _new_thread(app_session_factory, user, "test_two_steps")

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        thread = await session.get(AiThread, thread_id)
        assert thread is not None
        runtime = GraphRuntime(session, user.tenant_id)

        original = runtime._record_step

        async def cancel_after_first(*args: Any, **kwargs: Any) -> None:
            await original(*args, **kwargs)
            if thread.step_count == 1:
                thread.status = ThreadStatus.CANCELLED.value
                await session.flush()

        runtime._record_step = cancel_after_first  # type: ignore[method-assign]
        result = await runtime.start(thread, {"question": "oi"})

    assert result.status == "error"
    steps = await _steps(app_session_factory, user, thread_id)
    assert [step.node for step in steps] == ["collect"], "o segundo nó não pode ter rodado"


async def test_vigesimo_sexto_passo_e_barrado(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 9: laço infinito custa dinheiro — o teto é a proteção."""
    user = await make_user()
    thread_id = await _new_thread(app_session_factory, user, "test_endless")

    result = await _run(app_session_factory, user, thread_id, {}, max_steps=5)

    assert result.status == "error"
    assert "passos" in (result.error or "")
    final = await _reload(app_session_factory, user, thread_id)
    assert final.step_count == 6  # os 5 permitidos + o passo de erro


async def test_passo_grande_guarda_referencia(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 8: acima de 100 KB, referência — não o documento inteiro."""
    user = await make_user()
    thread_id = await _new_thread(app_session_factory, user, "test_huge")

    await _run(app_session_factory, user, thread_id)

    steps = await _steps(app_session_factory, user, thread_id)
    assert steps[0].output is not None
    assert steps[0].output["truncated"] is True
    assert steps[0].output["size_bytes"] > 100 * 1024
    assert "output" in steps[0].output["keys"]


async def test_thread_de_outro_usuario_da_403_e_administrador_audita(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 11: colega não lê; ADMINISTRADOR lê para auditar, mas não age."""
    dono = await make_user(role=UserRole.COLABORADOR)
    colega = await make_user(tenant_id=dono.tenant_id, role=UserRole.COLABORADOR)
    admin = await make_user(tenant_id=dono.tenant_id, role=UserRole.ADMINISTRADOR)
    thread_id = await _new_thread(app_session_factory, dono, "test_interrupt")
    await _run(app_session_factory, dono, thread_id)

    negado = await client.get(f"/api/v1/ai/threads/{thread_id}", headers=auth_header(colega))
    assert negado.status_code == 403

    auditoria = await client.get(f"/api/v1/ai/threads/{thread_id}", headers=auth_header(admin))
    assert auditoria.status_code == 200
    assert auditoria.json()["status"] == "waiting_human"

    passos = await client.get(f"/api/v1/ai/threads/{thread_id}/steps", headers=auth_header(admin))
    assert passos.status_code == 200
    assert passos.json()["total"] >= 1

    # Auditar não é agir: aprovar a ação pendente continua sendo só do dono.
    tentativa = await client.post(
        f"/api/v1/ai/threads/{thread_id}/resume",
        json={"approved": True},
        headers=auth_header(admin),
    )
    assert tentativa.status_code == 403


async def test_rls_isola_threads_checkpoints_e_passos(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """CLAUDE.md §4: tenant A não enxerga nada de B nas três tabelas novas."""
    a = await make_user()
    b = await make_user()
    thread_id = await _new_thread(app_session_factory, a, "test_two_steps")
    await _run(app_session_factory, a, thread_id, {"question": "oi"})

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, b.tenant_id)
        assert (await session.scalars(select(AiThread))).all() == []
        assert (await session.scalars(select(AiStep))).all() == []
        assert (await session.scalars(select(AiCheckpoint))).all() == []

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, a.tenant_id)
        assert len((await session.scalars(select(AiCheckpoint))).all()) == 2


async def test_api_cria_executa_e_transmite_os_passos(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """O caminho HTTP completo: criar parado, assistir pelo SSE, ver os passos."""
    user = await make_user()
    criado = await client.post(
        "/api/v1/ai/threads",
        json={
            "graph_name": "test_two_steps",
            "input": {"question": "prazo?"},
            "autorun": False,
        },
        headers=auth_header(user),
    )
    assert criado.status_code == 201, criado.text
    thread_id = criado.json()["id"]
    assert criado.json()["status"] == "pending"

    async with client.stream(
        "GET", f"/api/v1/ai/threads/{thread_id}/stream", headers=auth_header(user)
    ) as stream:
        corpo = "".join([chunk async for chunk in stream.aiter_text()])

    assert corpo.count("event: step") == 2
    assert "event: done" in corpo

    detalhe = await client.get(f"/api/v1/ai/threads/{thread_id}", headers=auth_header(user))
    assert detalhe.json()["status"] == "done"
    assert detalhe.json()["output"] == {"answer": "PRAZO?"}
