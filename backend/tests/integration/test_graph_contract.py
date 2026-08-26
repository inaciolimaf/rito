"""Contrato dos grafos de agente (spec 090, alvo 3).

Os testes da 082 provaram que o **runtime** impõe teto de passos e timeout — mas com
grafos escritos para o teste, que se comportam. Este arquivo faz a pergunta que sobrou:
**os grafos de verdade, os que estão registrados e rodam em produção, respeitam?**

É um teste parametrizado pelo registro. Grafo novo entra aqui sozinho — e é isso que se
quer: quem registrar o quinto grafo descobre no CI, não no fim do mês.
"""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.graphs.base import GraphDeps
from app.ai.graphs.registry import get_graph, graph_names
from app.ai.runtime import MAX_STEPS, GraphRuntime
from app.ai.tools.base import ToolContext, tool_specs
from app.ai.tools.runner import ToolRunner
from app.core.rls import set_tenant_context
from app.domain.ai.features import FEATURE_KEYS
from app.domain.ai.models import AiThread, ThreadStatus
from app.domain.ai.service import AiRunner
from app.domain.users.models import User
from app.integrations.openrouter.types import (
    LLMChunk,
    LLMResponse,
    Message,
    ModelInfo,
    ToolCall,
    ToolSpec,
    Usage,
)
from tests.integration.conftest import SeededUser

pytestmark = pytest.mark.asyncio


class LoopingProvider:
    """O pior modelo possível dentro do contrato: pede ferramenta para sempre.

    É o cenário que custa dinheiro de verdade — não o erro, que para sozinho, mas o
    laço que parece progresso. Se o grafo não tiver teto, este provider roda até o
    orçamento acabar.
    """

    is_configured = True

    def __init__(self) -> None:
        self.calls = 0

    async def complete(
        self,
        *,
        messages: Sequence[Message],
        model: str,
        tools: Sequence[ToolSpec] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.calls += 1
        return LLMResponse(
            content=None,
            tool_calls=[
                ToolCall(id=f"call_{self.calls}", name="get_current_context", arguments={})
            ],
            usage=Usage(prompt_tokens=10, completion_tokens=5),
            model=model,
            finish_reason="tool_calls",
        )

    async def stream(self, **kwargs: object) -> AsyncIterator[LLMChunk]:  # pragma: no cover
        yield LLMChunk(kind="done")

    async def models(self) -> list[ModelInfo]:
        return []


class SlowProvider(LoopingProvider):
    """Modelo que não responde. O timeout do runtime é a única saída."""

    async def complete(self, **kwargs: Any) -> LLMResponse:
        import asyncio

        await asyncio.sleep(30)
        raise AssertionError("o timeout do runtime tinha de ter cortado antes")


async def _thread(
    sessions: async_sessionmaker[AsyncSession], user: SeededUser, graph_name: str
) -> uuid.UUID:
    async with sessions() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        thread = AiThread(
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            graph_name=graph_name,
            feature_key=get_graph(graph_name).feature_key,
            status=ThreadStatus.PENDING.value,
        )
        session.add(thread)
        await session.flush()
        return thread.id


async def _drive(
    sessions: async_sessionmaker[AsyncSession],
    user: SeededUser,
    graph_name: str,
    provider: Any,
    **runtime_kwargs: Any,
) -> Any:
    thread_id = await _thread(sessions, user, graph_name)
    async with sessions() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        thread = await session.get(AiThread, thread_id)
        assert thread is not None
        quem = await session.get(User, user.user_id)
        assert quem is not None
        ctx = ToolContext(session=session, tenant_id=user.tenant_id, user=quem)
        deps = GraphDeps(
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            llm=AiRunner(session, user.tenant_id, provider),
            feature_key=thread.feature_key,
            # As ferramentas de verdade: um laço que não executa nada não é o laço que
            # custa dinheiro.
            tools={spec.name: spec for spec in tool_specs(quem)},
            tool_runner=ToolRunner(ctx),
        )
        runtime = GraphRuntime(session, user.tenant_id, deps=deps, **runtime_kwargs)
        return await runtime.start(thread, {"question": "e aí?"})


def test_existe_pelo_menos_um_grafo_registrado() -> None:
    """Se o registro esvaziar, os testes parametrizados abaixo passariam sem rodar nada
    — a pior forma de teste verde."""
    assert graph_names()


@pytest.mark.parametrize("graph_name", graph_names())
def test_todo_grafo_declara_nome_e_feature_conhecida(graph_name: str) -> None:
    """A feature é o que decide modelo, temperatura e limite de tokens (alvo 3): um
    grafo apontando para feature inexistente rodaria sempre no padrão do ambiente, sem
    ninguém perceber."""
    graph = get_graph(graph_name)
    assert graph.name == graph_name
    assert graph.feature_key in FEATURE_KEYS


@pytest.mark.parametrize("graph_name", graph_names())
async def test_todo_grafo_para_no_teto_de_passos(
    graph_name: str,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 9 da 082, agora sobre os grafos reais. O teto usado aqui é menor que os 25
    de produção só para o teste caber no orçamento — o que se prova é que o laço PARA,
    e o número vem do runtime, não do grafo."""
    user = await make_user()
    provider = LoopingProvider()

    resultado = await _drive(app_session_factory, user, graph_name, provider, max_steps=6)

    assert resultado.status == "error"
    assert "passos" in (resultado.error or "")
    assert provider.calls <= 6, "o modelo não pode ser chamado depois do teto"


@pytest.mark.parametrize("graph_name", graph_names())
async def test_todo_grafo_respeita_o_timeout_de_no(
    graph_name: str,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 5 da 082: um nó pendurado numa chamada que não volta não pode segurar a
    execução inteira. Quem corta é o runtime — nenhum grafo precisa lembrar disso."""
    user = await make_user()

    resultado = await _drive(
        app_session_factory, user, graph_name, SlowProvider(), node_timeout_s=0.05
    )

    assert resultado.status == "error"
    assert "excedeu" in (resultado.error or "") or "timeout" in (resultado.error or "").lower()


def test_o_teto_de_producao_continua_em_25_passos() -> None:
    """O número é da spec 082, não uma constante qualquer: aumentá-lo é uma decisão de
    custo, e passa por aqui."""
    assert MAX_STEPS == 25
