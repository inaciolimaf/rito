"""Timeout de nó sem corromper a sessão (spec 103 — dívida técnica nº 21).

O caso que este arquivo cobre é o que a 082 nunca cobriu e a 092 contornou baixando o
timeout do teste de contrato: o `asyncio.wait_for` da regra 5 corta **onde a corrotina
estiver**, e se ela estiver numa query o asyncpg invalida a CONEXÃO. A partir daí a
sessão de quem chamou não escreve mais nada — inclusive o passo de erro que existe para
registrar exatamente esta falha.

O grafo daqui roda `pg_sleep` **na sessão do runtime**, de propósito: é a única forma de
provar que o registro sobrevive, porque é a única forma de envenenar a sessão de verdade.
"""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import pytest
from httpx import AsyncClient
from langgraph.graph import END, StateGraph
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.graphs.base import GraphDeps, GraphState
from app.ai.graphs.registry import register_graph
from app.ai.runtime import GraphRuntime, RuntimeSessionLostError
from app.core.rls import set_tenant_context
from app.domain.ai.copilot import CopilotService
from app.domain.ai.models import AiCheckpoint, AiStep, AiThread, ThreadStatus
from app.domain.users.models import User
from app.integrations.openrouter.types import LLMChunk, LLMResponse, ModelInfo
from tests.integration.conftest import SeededUser, auth_header

pytestmark = pytest.mark.asyncio

# Curto o bastante para o corte cair DENTRO do `pg_sleep`, longo o bastante para o nó
# ter começado. O `pg_sleep` é de 3 s só para não haver dúvida sobre quem corta primeiro.
_TIMEOUT_S = 0.3
_SLEEP_SECONDS = 3
_GRAPH = "test_slow_query"


class _Graph:
    """Mesmo molde dos grafos de teste da 082: nome, feature e um builder."""

    def __init__(self, name: str, builder: Callable[[GraphDeps], Any]) -> None:
        self.name = name
        self.feature_key = "copilot"
        self._builder = builder

    def build(self, deps: GraphDeps) -> Any:
        return self._builder(deps)


def _session_of(deps: GraphDeps) -> AsyncSession:
    """A sessão que o nó usa é a MESMA do runtime — chega pelo `tool_runner` no caminho
    real (083) e pelo `context` quando o teste monta as deps na mão."""
    if deps.tool_runner is not None:
        session: AsyncSession = deps.tool_runner.ctx.session
        return session
    return deps.context["session"]  # type: ignore[no-any-return]


def _slow_query(deps: GraphDeps) -> Any:
    """Um nó que consulta o banco e demora. Não é artificial: desde a 090, todo nó de
    verdade faz duas consultas (configuração da feature e teto de gasto) antes de falar
    com o modelo."""
    graph = StateGraph(GraphState)

    async def slow(state: GraphState) -> dict[str, Any]:
        await _session_of(deps).execute(text(f"SELECT pg_sleep({_SLEEP_SECONDS})"))
        del state
        return {"output": {"nunca": "chega aqui"}}

    graph.add_node("slow", slow)
    graph.set_entry_point("slow")
    graph.add_edge("slow", END)
    return graph.compile()


_GRAPH_DOIS_NOS = "test_fast_then_slow"


def _fast_then_slow(deps: GraphDeps) -> Any:
    """Um nó que TERMINA e outro que estoura — o cenário da dívida 27.

    O grafo de um nó só não serve para prová-la: sem passo anterior, não há o que o rollback
    da requisição possa levar embora.
    """
    graph = StateGraph(GraphState)

    async def rapido(state: GraphState) -> dict[str, Any]:
        del state
        return {"output": {"passo": "um"}}

    async def slow(state: GraphState) -> dict[str, Any]:
        await _session_of(deps).execute(text(f"SELECT pg_sleep({_SLEEP_SECONDS})"))
        del state
        return {"output": {"nunca": "chega aqui"}}

    graph.add_node("rapido", rapido)
    graph.add_node("slow", slow)
    graph.set_entry_point("rapido")
    graph.add_edge("rapido", "slow")
    graph.add_edge("slow", END)
    return graph.compile()


@pytest.fixture(autouse=True)
def _register_slow_graph() -> None:
    register_graph(_Graph(_GRAPH, _slow_query))
    register_graph(_Graph(_GRAPH_DOIS_NOS, _fast_then_slow))


@pytest.fixture
def _fast_node_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """O timeout de produção é de 300 s (regra 5) e a rota não o parametriza — trocar a
    classe que a rota instancia é mais honesto do que expor um parâmetro que só o teste
    usaria."""

    class _Impatient(GraphRuntime):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs.setdefault("node_timeout_s", _TIMEOUT_S)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("app.domain.ai.threads_router.GraphRuntime", _Impatient)


async def _committed_thread(
    sessions: async_sessionmaker[AsyncSession], user: SeededUser, graph_name: str = _GRAPH
) -> uuid.UUID:
    async with sessions() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        thread = AiThread(
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            graph_name=graph_name,
            feature_key="copilot",
            status=ThreadStatus.PENDING.value,
        )
        session.add(thread)
        await session.flush()
        return thread.id


async def _run_until_timeout(
    sessions: async_sessionmaker[AsyncSession], user: SeededUser, thread_id: uuid.UUID
) -> None:
    """Roda o grafo lento até o timeout cortar. A exceção sobe pelo `session.begin()`,
    que faz o `rollback` — é o mesmo caminho da dependência da rota."""
    async with sessions() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        thread = await session.get(AiThread, thread_id)
        assert thread is not None
        deps = GraphDeps(
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            llm=None,
            feature_key="copilot",
            context={"session": session},
        )
        runtime = GraphRuntime(session, user.tenant_id, deps=deps, node_timeout_s=_TIMEOUT_S)
        await runtime.start(thread, {"pergunta": "quanto tempo?"})


async def _steps(
    sessions: async_sessionmaker[AsyncSession], user: SeededUser, thread_id: uuid.UUID
) -> list[AiStep]:
    async with sessions() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        stmt = select(AiStep).where(AiStep.thread_id == thread_id).order_by(AiStep.step)
        return list((await session.scalars(stmt)).all())


# ------------------------------------------------------------------------- runtime


@pytest.mark.commits
async def test_timeout_dentro_de_query_grava_o_passo_de_erro(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """O aceite da 103. Antes desta spec, o `_fail` morria com `PendingRollbackError` e
    a execução que estourou o tempo não conseguia registrar que estourou o tempo."""
    user = await make_user()
    thread_id = await _committed_thread(app_session_factory, user)

    # A sessão de quem chamou morreu com a query cancelada, e o runtime diz isso em vez
    # de devolver um resultado como se nada tivesse acontecido. Quem devolve a conexão é
    # quem abriu a transação — aqui o `session.begin()`, na aplicação a dependência da
    # rota; é por isso que a exceção sobe em vez de o runtime dar `rollback` sozinho.
    with pytest.raises(RuntimeSessionLostError):
        await _run_until_timeout(app_session_factory, user, thread_id)

    passos = await _steps(app_session_factory, user, thread_id)
    assert [(passo.node, passo.kind) for passo in passos] == [("timeout", "error")]
    assert "excedeu" in (passos[0].error or "")
    # Fora de banda continua sendo dentro do tenant: a sessão de registro seta o
    # `app.tenant_id` como qualquer outra, senão o RLS barraria o INSERT.
    assert passos[0].tenant_id == user.tenant_id

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        final = await session.get(AiThread, thread_id)
        assert final is not None
        assert final.status == ThreadStatus.ERROR.value
        assert final.finished_at is not None
        assert "excedeu" in (final.error or "")


@pytest.mark.commits
async def test_o_registro_fora_de_banda_nao_vaza_para_outro_tenant(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """CLAUDE.md §4 vale também para a sessão que o runtime abre sozinho — é uma sessão
    nova, e sessão nova sem contexto de tenant é exatamente como o RLS é furado."""
    dono = await make_user()
    outro = await make_user()
    thread_id = await _committed_thread(app_session_factory, dono)

    with pytest.raises(RuntimeSessionLostError):
        await _run_until_timeout(app_session_factory, dono, thread_id)

    assert await _steps(app_session_factory, dono, thread_id)
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, outro.tenant_id)
        assert (await session.scalars(select(AiStep))).all() == []


# ---------------------------------------------------------------------------- HTTP


@pytest.mark.commits
async def test_autorun_devolve_503_e_o_thread_sobrevive_com_o_erro(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    _fast_node_timeout: None,
) -> None:
    """O caso que a dívida chamava de pior: `POST /ai/threads` com `autorun=true`
    criava e executava na MESMA transação, então o rollback levaria junto a linha que o
    registro da falha precisa atualizar. Agora o thread é comitado antes de rodar — ele
    fica lá, em `error`, e a requisição morre em 503 em vez de morrer calada."""
    user = await make_user()

    resposta = await client.post(
        "/api/v1/ai/threads",
        json={"graph_name": _GRAPH, "autorun": True, "input": {"pergunta": "e aí?"}},
        headers=auth_header(user),
    )

    assert resposta.status_code == 503

    lista = await client.get("/api/v1/ai/threads", headers=auth_header(user))
    assert lista.status_code == 200
    threads = lista.json()["items"]
    assert len(threads) == 1, "o thread tem que sobreviver ao rollback da requisição"
    assert threads[0]["status"] == ThreadStatus.ERROR.value

    passos = await client.get(
        f"/api/v1/ai/threads/{threads[0]['id']}/steps", headers=auth_header(user)
    )
    assert passos.status_code == 200
    assert [item["kind"] for item in passos.json()["items"]] == ["error"]


@pytest.mark.commits
async def test_sse_conta_a_falha_ao_cliente_em_vez_de_cortar_a_conexao(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    _fast_node_timeout: None,
) -> None:
    """No SSE a resposta já começou quando o timeout corta — 503 não cabe mais. O que
    cabe é o evento `error`, e é o que o cliente recebe."""
    user = await make_user()
    criado = await client.post(
        "/api/v1/ai/threads",
        json={"graph_name": _GRAPH, "autorun": False, "input": {}},
        headers=auth_header(user),
    )
    assert criado.status_code == 201
    thread_id = criado.json()["id"]

    fluxo = await client.get(f"/api/v1/ai/threads/{thread_id}/stream", headers=auth_header(user))

    assert fluxo.status_code == 200
    assert "event: error" in fluxo.text

    depois = await client.get(f"/api/v1/ai/threads/{thread_id}", headers=auth_header(user))
    assert depois.json()["status"] == ThreadStatus.ERROR.value


async def test_conversa_nova_do_copiloto_e_comitada_antes_de_rodar(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """O copiloto (085) tem a mesma forma do `autorun`: cria o thread e roda o turno na
    transação da requisição. Com a fábrica de sessão injetada, a conversa existe para
    QUALQUER conexão antes de o turno começar — que é a condição para o registro fora
    de banda ter onde escrever."""
    user = await make_user()

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        quem = await session.get(User, user.user_id)
        assert quem is not None
        service = CopilotService(
            session=session,
            tenant_id=user.tenant_id,
            provider=_ConfiguredProvider(),
            thread_sessions=app_session_factory,
        )
        thread, _state = await service.start_turn(
            user=quem, thread_id=None, message="e aí?", context=None
        )

        # Outra conexão, outra transação: só enxerga o que já foi comitado.
        async with app_session_factory() as espiao, espiao.begin():
            await set_tenant_context(espiao, user.tenant_id)
            visto = await espiao.get(AiThread, thread.id)
            assert visto is not None, "a conversa tem que existir antes de o turno rodar"


class _ConfiguredProvider:
    """Só para o service passar pelo `ensure_available` — nenhum turno roda aqui, e
    nenhuma chamada de LLM acontece (CLAUDE.md §3). Implementa o protocolo inteiro
    porque o mock de uma interface É uma implementação dela (CLAUDE.md §5, LSP)."""

    is_configured = True

    async def complete(self, **kwargs: Any) -> LLMResponse:  # pragma: no cover
        raise AssertionError("nenhum turno roda neste teste")

    async def stream(self, **kwargs: Any) -> AsyncIterator[LLMChunk]:  # pragma: no cover
        raise AssertionError("nenhum turno roda neste teste")
        yield LLMChunk(kind="done")

    async def models(self) -> list[ModelInfo]:  # pragma: no cover
        return []


@pytest.mark.commits
async def test_passos_anteriores_sobrevivem_ao_rollback_da_requisicao(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Dívida 27: o passo já registrado sumia quando o timeout matava a sessão.

    Antes da spec 124, `_record_step` escrevia na transação de QUEM CHAMOU. Uma execução que
    estourasse o tempo dentro de uma query gravava o passo de erro fora de banda e terminava
    em `error` — mas os passos anteriores iam embora com o rollback dessa transação. O
    resultado era um buraco na numeração: `ai_steps` com um único passo de erro numerado 2,
    sem o 1. Quem auditava via o fim sem o meio, e um `ai_checkpoints` que só vale se a
    requisição inteira der certo não é checkpoint.

    Com o commit por passo, o nó que concluiu fica gravado mesmo quando o seguinte derruba a
    sessão — que é o que «retomar de onde parou» exige para significar alguma coisa.
    """
    user = await make_user()
    thread_id = await _committed_thread(app_session_factory, user, graph_name=_GRAPH_DOIS_NOS)

    with pytest.raises(RuntimeSessionLostError):
        await _run_until_timeout(app_session_factory, user, thread_id)

    passos = await _steps(app_session_factory, user, thread_id)
    nos = [(passo.step, passo.node, passo.kind) for passo in passos]
    assert nos == [(1, "rapido", "node"), (2, "timeout", "error")], (
        "o passo do nó que CONCLUIU não sobreviveu ao rollback da requisição — "
        f"`_record_step` voltou a escrever na transação de quem chama (dívida 27). Veio: {nos}"
    )

    # O checkpoint do passo bom também precisa estar lá: é dele que a retomada parte.
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        checkpoints = list(
            (
                await session.scalars(
                    select(AiCheckpoint)
                    .where(AiCheckpoint.thread_id == thread_id)
                    .order_by(AiCheckpoint.step)
                )
            ).all()
        )
    # O `timeout` também tem checkpoint: quem o escreve é o registro fora de banda da spec
    # 103, e isso é anterior a esta correção. O que a dívida 27 pedia é o do nó CONCLUÍDO.
    assert [c.node for c in checkpoints] == ["rapido", "timeout"], (
        "sem checkpoint do nó concluído não há de onde retomar — é a metade da dívida 27 "
        f"que o `ai_checkpoints` existe para resolver. Veio: {[c.node for c in checkpoints]}"
    )
