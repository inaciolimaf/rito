"""Agentes de petição (spec 087).

O modelo é sempre um fake — o que se verifica é o que o AGENTE faz em volta dele:
coleta contexto por ferramenta (sem RAG), respeita a estrutura do modelo do escritório,
remove citação sem respaldo e não salva nada no processo por conta própria.
"""

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.legal_agents.catalog import AGENT_SEEDS
from app.domain.legal_agents.citations import REMOVED_MARKER
from app.domain.legal_agents.models import AgentGeneration, LegalAgent
from app.domain.templates.models import Template
from app.domain.users.models import UserRole
from app.integrations.openrouter.types import LLMResponse, Usage
from tests.integration.conftest import SeededUser, auth_header
from tests.integration.test_ai_copilot import ScriptedProvider, _use
from tests.integration.test_lawsuits import (
    _auth_header,
    _create_customer,
    _create_lawsuit,
    _create_lawsuit_type,
    _create_stage,
)


def _draft(html: str) -> LLMResponse:
    return LLMResponse(
        content=html,
        usage=Usage(prompt_tokens=1200, completion_tokens=800),
        model="fabricante-x/modelo-y",
        finish_reason="stop",
    )


async def _setup(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> tuple[SeededUser, str, str]:
    """Escritório com um processo — e o id do agente trabalhista de sistema."""
    user = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(user)
    type_id, _group = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    customer_id = await _create_customer(client, headers, "Joana Reclamante")
    lawsuit = await _create_lawsuit(
        client,
        headers,
        user_id=str(user.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
        folder="PASTA-TRAB",
        parties=[{"customer_id": customer_id, "pole": "ATIVO", "is_client": True}],
    )
    agentes = await client.get("/api/v1/legal-agents", headers=headers)
    assert agentes.status_code == 200, agentes.text
    trabalhista = next(item for item in agentes.json()["items"] if item["code"] == "trab-1")
    return user, str(lawsuit["id"]), trabalhista["id"]


async def _generate(
    client: AsyncClient, user: SeededUser, agent_id: str, lawsuit_id: str, **extra: Any
) -> dict[str, Any]:
    resposta = await client.post(
        f"/api/v1/legal-agents/{agent_id}/generate",
        json={"lawsuit_id": lawsuit_id, **extra},
        headers=auth_header(user),
    )
    assert resposta.status_code == 200, resposta.text
    return dict(resposta.json())


@pytest.fixture(autouse=True)
def _reset_overrides() -> Any:
    from app.domain.ai.router import get_llm_provider
    from app.main import app

    yield
    app.dependency_overrides.pop(get_llm_provider, None)


def test_seed_cria_os_dezenove_agentes() -> None:
    """O catálogo é código versionado: mudar um prompt é pull request, não UPDATE."""
    assert len(AGENT_SEEDS) == 19
    assert len({seed.code for seed in AGENT_SEEDS}) == 19
    # Regra 6: a proibição vale para todos, sem exceção.
    for seed in AGENT_SEEDS:
        prompt = seed.system_prompt()
        assert "NÃO cite jurisprudência" in prompt
        assert "MINUTA" in prompt


async def test_os_agentes_de_sistema_aparecem_para_o_escritorio(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user()
    _use(ScriptedProvider())

    resposta = await client.get("/api/v1/legal-agents", headers=auth_header(user))

    assert resposta.status_code == 200
    assert resposta.json()["total"] == 19
    areas = {item["practice_area"] for item in resposta.json()["items"]}
    assert "Direito do Trabalho" in areas
    assert all(item["is_customized"] is False for item in resposta.json()["items"])


async def test_geracao_coleta_contexto_por_ferramentas(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 1: sem RAG — o contexto vem de consulta ao banco, feita na hora, com o RLS
    de quem pediu."""
    user, lawsuit_id, agent_id = await _setup(client, make_user)
    provider = ScriptedProvider(script=[_draft("<h1>RECLAMAÇÃO TRABALHISTA</h1><p>Dos fatos.</p>")])
    _use(provider)

    corpo = await _generate(client, user, agent_id, lawsuit_id)

    prompt = provider.prompts[0][-1].content
    assert "get_lawsuit" in prompt
    assert "get_lawsuit_timeline" in prompt
    assert "PASTA-TRAB" in prompt, "o contexto real do processo tem que estar no prompt"
    # Regra 8: a UI mostra o que o agente consultou, em português.
    assert corpo["tool_labels"] == ["abrindo o processo", "lendo o andamento do processo"]

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        from app.domain.ai.models import AiToolCall

        chamadas = [row.tool_name for row in (await session.scalars(select(AiToolCall))).all()]
    assert chamadas == ["get_lawsuit", "get_lawsuit_timeline"]


async def test_modelo_do_escritorio_define_a_estrutura(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 2: o modelo dá a estrutura, o agente escreve o conteúdo."""
    user, lawsuit_id, agent_id = await _setup(client, make_user)
    criado = await client.post(
        "/api/v1/templates",
        json={
            "name": "Reclamação padrão do escritório",
            "type": "PETICAO",
            "content": "<h2>I - DOS FATOS</h2><h2>II - DO DIREITO</h2><p>{{cliente.nome}}</p>",
        },
        headers=auth_header(user),
    )
    assert criado.status_code == 201, criado.text
    provider = ScriptedProvider(script=[_draft("<h2>I - DOS FATOS</h2><p>Conteúdo.</p>")])
    _use(provider)

    corpo = await _generate(client, user, agent_id, lawsuit_id, template_id=criado.json()["id"])

    prompt = provider.prompts[0][-1].content
    assert "I - DOS FATOS" in prompt
    assert "mantenha a variável como está" in prompt
    assert corpo["template_used_id"] == criado.json()["id"]


async def test_sem_modelo_usa_a_estrutura_padrao_da_area(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user, lawsuit_id, agent_id = await _setup(client, make_user)
    provider = ScriptedProvider(script=[_draft("<h1>Peça</h1>")])
    _use(provider)

    corpo = await _generate(client, user, agent_id, lawsuit_id)

    assert "Não há modelo do escritório" in provider.prompts[0][-1].content
    assert corpo["template_used_id"] is None
    # A estrutura da área vem do prompt de sistema do agente.
    assert "liquidação" in provider.prompts[0][0].content


async def test_saida_e_html_pronto_para_o_editor(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 3: o editor da 065 guarda HTML — a minuta sai no mesmo formato."""
    user, lawsuit_id, agent_id = await _setup(client, make_user)
    _use(ScriptedProvider(script=[_draft("<h1>RECLAMAÇÃO</h1><p>Texto.</p>")]))

    corpo = await _generate(client, user, agent_id, lawsuit_id)

    assert corpo["content"]["format"] == "html"
    assert corpo["content"]["html"].startswith("<h1>")


async def test_nao_inventa_citacao_fora_do_contexto(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 6 — o teste que a spec marca como essencial.

    O prompt proíbe; este teste prova que a proibição é cumprida mesmo quando o modelo
    desobedece, porque quem cumpre é o código.
    """
    user, lawsuit_id, agent_id = await _setup(client, make_user)
    _use(
        ScriptedProvider(
            script=[
                _draft(
                    "<p>Conforme a Súmula 331 do TST e o REsp 1.234.567/SP, o pedido "
                    "deve ser julgado procedente.</p>"
                )
            ]
        )
    )

    corpo = await _generate(client, user, agent_id, lawsuit_id)

    html = corpo["content"]["html"]
    assert "Súmula 331" not in html
    assert "1.234.567" not in html
    assert REMOVED_MARKER in html
    assert {item["kind"] for item in corpo["warnings"]} == {"súmula", "recurso"}


async def test_instrucoes_do_usuario_tem_precedencia(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 5: o que o advogado pediu vem por último e manda — menos sobre as regras
    de segurança."""
    user, lawsuit_id, agent_id = await _setup(client, make_user)
    provider = ScriptedProvider(script=[_draft("<p>Ok.</p>")])
    _use(provider)

    await _generate(
        client,
        user,
        agent_id,
        lawsuit_id,
        instructions="Foque no adicional de insalubridade e seja breve.",
    )

    prompt = provider.prompts[0][-1].content
    assert prompt.index("INSTRUÇÕES DO ADVOGADO") > prompt.index("CONTEXTO DO PROCESSO")
    assert "adicional de insalubridade" in prompt
    assert "exceto sobre as regras inegociáveis" in prompt


async def test_registra_modelo_e_tokens(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 7: cada geração registra o que custou."""
    user, lawsuit_id, agent_id = await _setup(client, make_user)
    _use(ScriptedProvider(script=[_draft("<p>Peça.</p>")]))

    corpo = await _generate(client, user, agent_id, lawsuit_id)

    assert corpo["model"] == "fabricante-x/modelo-y"
    assert corpo["tokens_used"] == 2000
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        from app.domain.ai.models import AiUsage

        usos = list((await session.scalars(select(AiUsage))).all())
    # A contabilidade da 081 continua valendo: a geração aparece no painel de consumo.
    assert [uso.feature_key for uso in usos] == ["petition_draft"]


async def test_agente_desabilitado_nao_aparece_nem_gera(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
    admin_engine: Any,
) -> None:
    """Regra 9."""
    user, lawsuit_id, agent_id = await _setup(client, make_user)
    async with admin_engine.begin() as conn:
        from sqlalchemy import text as sql_text

        await conn.execute(
            sql_text("UPDATE legal_agents SET is_enabled = false WHERE id = :id"),
            {"id": uuid.UUID(agent_id)},
        )
    _use(ScriptedProvider(script=[_draft("<p>Não deveria gerar.</p>")]))

    listagem = await client.get("/api/v1/legal-agents", headers=auth_header(user))
    tentativa = await client.post(
        f"/api/v1/legal-agents/{agent_id}/generate",
        json={"lawsuit_id": lawsuit_id},
        headers=auth_header(user),
    )

    assert all(item["code"] != "trab-1" for item in listagem.json()["items"])
    assert tentativa.status_code == 404

    async with admin_engine.begin() as conn:
        from sqlalchemy import text as sql_text

        await conn.execute(
            sql_text("UPDATE legal_agents SET is_enabled = true WHERE id = :id"),
            {"id": uuid.UUID(agent_id)},
        )


async def test_prompt_editavel_vira_copia_do_escritorio_e_restauravel(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 10: editar um agente de SISTEMA cria a cópia do escritório — um tenant não
    reescreve o prompt do vizinho."""
    user, _lawsuit_id, agent_id = await _setup(client, make_user)
    _use(ScriptedProvider())

    editado = await client.put(
        f"/api/v1/legal-agents/{agent_id}",
        json={"system_prompt": "Prompt do escritório, bem específico."},
        headers=auth_header(user),
    )

    assert editado.status_code == 200, editado.text
    assert editado.json()["is_customized"] is True
    assert editado.json()["system_prompt"] == "Prompt do escritório, bem específico."
    copia_id = editado.json()["id"]
    assert copia_id != agent_id

    # O agente de sistema segue intacto para os outros escritórios.
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        original = await session.get(LegalAgent, uuid.UUID(agent_id))
        assert original is not None
        assert original.tenant_id is None
        assert "Prompt do escritório" not in original.system_prompt

    restaurado = await client.put(
        f"/api/v1/legal-agents/{copia_id}",
        json={"restore_original": True},
        headers=auth_header(user),
    )
    assert restaurado.json()["system_prompt"].startswith("Você é um assistente")

    # A listagem mostra a cópia no lugar do agente de sistema, não os dois.
    listagem = await client.get("/api/v1/legal-agents", headers=auth_header(user))
    trabalhistas = [item for item in listagem.json()["items"] if item["code"] == "trab-1"]
    assert len(trabalhistas) == 1
    assert trabalhistas[0]["id"] == copia_id


async def test_minuta_nao_e_salva_sem_o_usuario_mandar(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 12: gerar é uma coisa, virar documento do escritório é outra."""
    user, lawsuit_id, agent_id = await _setup(client, make_user)
    _use(ScriptedProvider(script=[_draft("<h1>Minuta</h1><p>Texto.</p>")]))
    corpo = await _generate(client, user, agent_id, lawsuit_id)

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        antes = list((await session.scalars(select(Template))).all())
    assert antes == [], "gerar não pode criar documento no escritório"
    assert corpo["saved_template_id"] is None

    salvo = await client.post(
        f"/api/v1/agent-generations/{corpo['id']}/to-template",
        json={"name": "Reclamação — Joana"},
        headers=auth_header(user),
    )

    assert salvo.status_code == 200, salvo.text
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        depois = list((await session.scalars(select(Template))).all())
        geracao = await session.get(AgentGeneration, uuid.UUID(corpo["id"]))
    assert len(depois) == 1
    assert depois[0].name == "Reclamação — Joana"
    assert depois[0].content.startswith("<h1>")
    assert geracao is not None and geracao.saved_template_id == depois[0].id


async def test_timeout_da_geracao_vira_erro_claro(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 11: geração que passa do tempo devolve mensagem, não requisição pendurada."""
    user, lawsuit_id, agent_id = await _setup(client, make_user)

    class ProviderQueTrava(ScriptedProvider):
        async def complete(self, **kwargs: Any) -> LLMResponse:
            raise TimeoutError("o modelo não respondeu no tempo")

    _use(ProviderQueTrava())

    resposta = await client.post(
        f"/api/v1/legal-agents/{agent_id}/generate",
        json={"lawsuit_id": lawsuit_id},
        headers=auth_header(user),
    )

    assert resposta.status_code == 504
    assert "tempo limite" in resposta.json()["detail"]
