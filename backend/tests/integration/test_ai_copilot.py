"""Copiloto global (spec 085) — o LLM é sempre um fake que implementa `LLMProvider`.

O que se verifica aqui não é o que um modelo responderia (isso ninguém controla), e sim
o que o COPILOTO faz em volta da resposta: leva o contexto da tela, chama a ferramenta
certa, mostra a ação pendente sem executar, respeita o limite da conversa e não guarda
texto sem opt-in.
"""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.ai.copilot import MAX_MESSAGES_PER_THREAD
from app.domain.ai.models import AiAction, AiMessage, AiThread
from app.domain.ai.service import AiConfigService
from app.domain.users.models import UserRole
from app.integrations.openrouter.types import (
    LLMChunk,
    LLMNotConfiguredError,
    LLMResponse,
    Message,
    ModelInfo,
    ToolCall,
    ToolSpec,
    Usage,
)
from tests.integration.conftest import SeededUser, auth_header
from tests.integration.test_lawsuits import _auth_header, _create_customer


class ScriptedProvider:
    """Implementação de `LLMProvider` que segue um roteiro (LSP, CLAUDE.md §5).

    Guarda tudo o que recebeu — é assim que os testes conferem que o contexto da tela
    chegou ao prompt e que o catálogo de ferramentas foi oferecido.
    """

    def __init__(self, *, script: Sequence[LLMResponse] | None = None) -> None:
        self.is_configured = True
        self.script = list(script or [])
        self.prompts: list[list[Message]] = []
        self.models_used: list[str] = []
        self.tools_offered: list[list[str]] = []

    async def complete(
        self,
        *,
        messages: Sequence[Message],
        model: str,
        tools: Sequence[ToolSpec] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.prompts.append(list(messages))
        self.models_used.append(model)
        self.tools_offered.append([tool.name for tool in tools or []])
        if self.script:
            return self.script.pop(0)
        return LLMResponse(
            content="Certo.", usage=Usage(prompt_tokens=10, completion_tokens=5), model=model
        )

    async def stream(self, **kwargs: object) -> AsyncIterator[LLMChunk]:  # pragma: no cover
        yield LLMChunk(kind="done")

    async def models(self) -> list[ModelInfo]:
        return []


def _answer(text: str) -> LLMResponse:
    return LLMResponse(
        content=text,
        usage=Usage(prompt_tokens=10, completion_tokens=5),
        model="fabricante-x/modelo-y",
        finish_reason="stop",
    )


def _tool_call(name: str, arguments: dict[str, Any]) -> LLMResponse:
    return LLMResponse(
        content=None,
        tool_calls=[ToolCall(id="call_1", name=name, arguments=arguments)],
        usage=Usage(prompt_tokens=10, completion_tokens=5),
        model="fabricante-x/modelo-y",
        finish_reason="tool_calls",
    )


def _use(provider: object) -> None:
    from app.domain.ai.router import get_llm_provider
    from app.main import app

    app.dependency_overrides[get_llm_provider] = lambda: provider


@pytest.fixture(autouse=True)
def _clear_overrides() -> Any:
    from app.domain.ai.router import get_llm_provider
    from app.main import app

    yield
    app.dependency_overrides.pop(get_llm_provider, None)


async def _send(
    client: AsyncClient, user: SeededUser, message: str, **extra: Any
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/ai/copilot/message",
        json={"message": message, **extra},
        headers=auth_header(user),
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


async def test_mensagem_simples_responde_e_guarda_o_historico(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await make_user()
    _use(ScriptedProvider(script=[_answer("Você tem 3 prazos esta semana.")]))

    corpo = await _send(client, user, "quantos prazos eu tenho?")

    assert corpo["reply"] == "Você tem 3 prazos esta semana."
    assert corpo["status"] == "done"
    # Regra 6: o título sai da primeira pergunta.
    assert corpo["title"] == "quantos prazos eu tenho?"

    detalhe = await client.get(
        f"/api/v1/ai/copilot/threads/{corpo['thread_id']}", headers=auth_header(user)
    )
    assert [item["role"] for item in detalhe.json()["items"]] == ["user", "assistant"]


async def test_contexto_da_tela_entra_no_prompt(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 1: é o que faz "esse cliente" ser respondível sem repetir de quem se fala."""
    user = await make_user()
    provider = ScriptedProvider(script=[_answer("Ele deve R$ 1.200,00.")])
    _use(provider)
    customer_id = str(uuid.uuid4())

    await _send(
        client,
        user,
        "quanto esse cliente deve?",
        context={"route": "/customers/123", "customer_id": customer_id},
    )

    system = provider.prompts[0][0]
    assert system.role == "system"
    assert customer_id in system.content
    assert "/customers/123" in system.content


async def test_pergunta_sobre_dado_real_chama_a_ferramenta_certa(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Sem RAG: o dado vem de uma consulta ao banco, feita na hora, com o RLS do
    usuário (specs 083 e 085)."""
    user = await make_user(role=UserRole.GESTOR)
    nome = f"Joana Ré {uuid.uuid4().hex[:6]}"
    await _create_customer(client, _auth_header(user), nome)
    provider = ScriptedProvider(
        script=[
            _tool_call("search_customers", {"query": nome}),
            _answer(f"Encontrei o contato {nome}."),
        ]
    )
    _use(provider)

    corpo = await _send(client, user, f"procure o contato {nome}")

    assert corpo["reply"] == f"Encontrei o contato {nome}."
    # Regra 3: o indicador é em português, não o nome técnico da ferramenta.
    assert corpo["tool_labels"] == ["consultando contatos"]
    # A segunda ida ao modelo já leva o resultado da consulta.
    resultado = provider.prompts[1][-1]
    assert resultado.role == "tool"
    assert nome in resultado.content
    assert "search_customers" in provider.tools_offered[0]


async def test_acao_de_escrita_fica_pendente_no_chat_sem_gravar(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regras 4 e 11: a ação aparece inline, nada é gravado, e o copiloto NÃO diz que
    fez — diz que preparou."""
    user = await make_user(role=UserRole.GESTOR)
    origem = await _origin_id(client, app_session_factory, user)
    _use(
        ScriptedProvider(
            script=[
                _tool_call(
                    "create_customer",
                    {"name": "Cliente Novo", "type": "PF", "origin_id": origem},
                )
            ]
        )
    )

    corpo = await _send(client, user, "cadastre o cliente Cliente Novo")

    assert corpo["status"] == "waiting_human"
    assert corpo["pending_action"]["kind"] == "create_customer"
    assert "Nada foi gravado ainda" in corpo["reply"]
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        acoes = list((await session.scalars(select(AiAction))).all())
        mensagens = list((await session.scalars(select(AiMessage))).all())
    assert len(acoes) == 1 and acoes[0].status == "pending"
    # Regra 4: a mensagem do assistente aponta para a ação — é o que a UI usa para
    # desenhar o preview inline.
    assert any(item.action_id == acoes[0].id for item in mensagens)


async def test_aprovar_pelo_chat_executa_e_recusar_e_reconhecido(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regras 4 e 11: aprovar no chat executa de verdade; recusar fica registrado e o
    agente é informado na volta."""
    user = await make_user(role=UserRole.GESTOR)
    origem = await _origin_id(client, app_session_factory, user)
    _use(
        ScriptedProvider(
            script=[
                _tool_call(
                    "create_customer",
                    {"name": "Cliente Aprovado no Chat", "type": "PF", "origin_id": origem},
                )
            ]
        )
    )
    corpo = await _send(client, user, "cadastre o Cliente Aprovado no Chat")
    action_id = corpo["pending_action"]["action_id"]

    aprovado = await client.post(
        f"/api/v1/ai/actions/{action_id}/approve", headers=auth_header(user)
    )
    assert aprovado.status_code == 200
    assert aprovado.json()["status"] == "executed"

    # Agora uma recusa, no mesmo escritório.
    _use(
        ScriptedProvider(
            script=[
                _tool_call(
                    "create_customer",
                    {"name": "Cliente Recusado no Chat", "type": "PF", "origin_id": origem},
                )
            ]
        )
    )
    outro = await _send(client, user, "cadastre o Cliente Recusado no Chat")
    recusado = await client.post(
        f"/api/v1/ai/actions/{outro['pending_action']['action_id']}/reject",
        json={"reason": "cliente já existe"},
        headers=auth_header(user),
    )
    assert recusado.status_code == 200
    assert recusado.json()["rejection_reason"] == "cliente já existe"


async def test_sugestoes_variam_por_tela(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 5."""
    user = await make_user()
    _use(ScriptedProvider())

    financeiro = await client.get(
        "/api/v1/ai/copilot/suggestions",
        params={"context": "/transactions"},
        headers=auth_header(user),
    )
    processo = await client.get(
        "/api/v1/ai/copilot/suggestions",
        params={"context": "/lawsuits/abc"},
        headers=auth_header(user),
    )

    assert "Quem está inadimplente?" in financeiro.json()["items"]
    assert "Resumir o andamento deste processo" in processo.json()["items"]
    assert financeiro.json()["items"] != processo.json()["items"]


async def test_conversa_longa_sugere_comecar_outra(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 8: em vez de deixar a conversa crescer sem fim (e ficar cara e pior), o
    copiloto recusa e explica."""
    user = await make_user()
    _use(ScriptedProvider(script=[_answer("Certo.")]))
    corpo = await _send(client, user, "primeira pergunta")
    thread_id = corpo["thread_id"]

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        for _ in range(MAX_MESSAGES_PER_THREAD):
            session.add(
                AiMessage(
                    tenant_id=user.tenant_id,
                    thread_id=uuid.UUID(thread_id),
                    role="user",
                    content=None,
                )
            )

    resposta = await client.post(
        "/api/v1/ai/copilot/message",
        json={"message": "mais uma", "thread_id": thread_id},
        headers=auth_header(user),
    )

    assert resposta.status_code == 409
    assert "nova" in resposta.json()["detail"]


async def test_troca_de_modelo_vale_para_o_thread(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 9: a escolha do usuário no painel vence a configuração da feature."""
    user = await make_user()
    provider = ScriptedProvider(script=[_answer("ok"), _answer("ok de novo")])
    _use(provider)

    primeiro = await _send(client, user, "olá", model="fabricante-z/modelo-escolhido")
    await client.post(
        "/api/v1/ai/copilot/message",
        json={"message": "e agora?", "thread_id": primeiro["thread_id"]},
        headers=auth_header(user),
    )

    assert primeiro["model"] == "fabricante-z/modelo-escolhido"
    # Vale para as duas idas ao modelo, inclusive na mensagem seguinte do mesmo thread.
    assert provider.models_used == [
        "fabricante-z/modelo-escolhido",
        "fabricante-z/modelo-escolhido",
    ]


async def test_sem_chave_ou_com_a_feature_desligada_o_copiloto_some(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 10: 409 com motivo — a UI esconde o painel em vez de mostrar botão quebrado."""
    user = await make_user(role=UserRole.GESTOR)

    class SemChave(ScriptedProvider):
        def __init__(self) -> None:
            super().__init__()
            self.is_configured = False

        async def models(self) -> list[ModelInfo]:
            raise LLMNotConfiguredError("sem chave")

    _use(SemChave())
    sem_chave = await client.post(
        "/api/v1/ai/copilot/message", json={"message": "oi"}, headers=auth_header(user)
    )
    assert sem_chave.status_code == 409
    assert "chave" in sem_chave.json()["detail"]

    # Com chave, mas com a feature desligada pelo escritório.
    _use(ScriptedProvider(script=[_answer("oi")]))
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        service = AiConfigService(session=session, tenant_id=user.tenant_id)
        await service.save(
            feature_key="copilot",
            model="fabricante-x/modelo-y",
            fallback_model=None,
            temperature=0.2,
            max_tokens=None,
            is_enabled=False,
            store_prompts=False,
            actor_id=user.user_id,
        )
    desligado = await client.post(
        "/api/v1/ai/copilot/message", json={"message": "oi"}, headers=auth_header(user)
    )
    assert desligado.status_code == 409
    assert "desligado" in desligado.json()["detail"]


async def test_conversa_de_outro_usuario_da_403(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    dono = await make_user()
    colega = await make_user(tenant_id=dono.tenant_id)
    _use(ScriptedProvider(script=[_answer("ok")]))
    corpo = await _send(client, dono, "minha conversa")

    lido = await client.get(
        f"/api/v1/ai/copilot/threads/{corpo['thread_id']}", headers=auth_header(colega)
    )
    apagado = await client.delete(
        f"/api/v1/ai/copilot/threads/{corpo['thread_id']}", headers=auth_header(colega)
    )

    assert lido.status_code == 403
    assert apagado.status_code == 403


async def test_sem_opt_in_o_historico_guarda_so_metadados(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 13 (e regra 13 da 081): a conversa não fica gravada sem o tenant pedir."""
    user = await make_user(role=UserRole.GESTOR)
    _use(ScriptedProvider(script=[_answer("resposta secreta")]))

    await _send(client, user, "pergunta secreta")

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        mensagens = list((await session.scalars(select(AiMessage))).all())
    assert len(mensagens) == 2
    assert all(item.content is None for item in mensagens)

    # Com opt-in, o texto passa a ser guardado.
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        service = AiConfigService(session=session, tenant_id=user.tenant_id)
        await service.save(
            feature_key="copilot",
            model="fabricante-x/modelo-y",
            fallback_model=None,
            temperature=0.2,
            max_tokens=None,
            is_enabled=True,
            store_prompts=True,
            actor_id=user.user_id,
        )
    _use(ScriptedProvider(script=[_answer("agora pode guardar")]))
    await _send(client, user, "pergunta guardada")

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        textos = [
            item.content
            for item in (await session.scalars(select(AiMessage))).all()
            if item.content
        ]
    assert "pergunta guardada" in textos
    assert "agora pode guardar" in textos


async def test_stream_emite_ferramenta_resposta_e_fim(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regras 2 e 3: o SSE conta o que está acontecendo enquanto acontece."""
    user = await make_user(role=UserRole.GESTOR)
    nome = f"Contato SSE {uuid.uuid4().hex[:6]}"
    await _create_customer(client, _auth_header(user), nome)
    _use(ScriptedProvider(script=[_answer("Primeira resposta.")]))
    corpo = await _send(client, user, "abrir conversa")

    _use(
        ScriptedProvider(
            script=[
                _tool_call("search_customers", {"query": nome}),
                _answer("Achei o contato."),
            ]
        )
    )
    async with client.stream(
        "GET",
        f"/api/v1/ai/copilot/stream/{corpo['thread_id']}",
        params={"message": f"procure {nome}"},
        headers=auth_header(user),
    ) as stream:
        eventos = "".join([chunk async for chunk in stream.aiter_text()])

    assert "event: tool" in eventos
    assert "consultando contatos" in eventos
    assert "event: message" in eventos
    assert "Achei o contato." in eventos
    assert eventos.strip().endswith("}") and "event: done" in eventos


async def _origin_id(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    user: SeededUser,
) -> str:
    from app.domain.customers.models import Customer

    customer_id = await _create_customer(client, _auth_header(user), "Semente de Origem")
    async with sessions() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        customer = await session.get(Customer, uuid.UUID(customer_id))
        assert customer is not None
        return str(customer.origin_id)


async def test_thread_inativo_e_arquivado(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 7: 30 dias sem uso arquiva — o expurgo dos 90 dias é do worker da 082."""
    from datetime import UTC, datetime, timedelta

    from app.domain.ai.copilot import CopilotService

    user = await make_user()
    _use(ScriptedProvider(script=[_answer("ok")]))
    corpo = await _send(client, user, "conversa que vai esfriar")

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        service = CopilotService(
            session=session, tenant_id=user.tenant_id, provider=ScriptedProvider()
        )
        arquivados = await service.archive_inactive(now=datetime.now(UTC) + timedelta(days=31))

    assert arquivados == 1
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        thread = await session.get(AiThread, uuid.UUID(corpo["thread_id"]))
        assert thread is not None and thread.archived_at is not None
