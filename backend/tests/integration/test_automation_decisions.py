"""Decisão por LLM dentro da automação (spec 094 §9).

Duas invariantes guiam o arquivo, e as duas valem quando tudo dá errado: **a IA nunca
trava a automação** (regra 5) e **o raciocínio é sempre gravado** (regra 4), inclusive o
do fallback — "caiu no padrão porque o modelo não respondeu" é uma explicação, e é a que
o auditor precisa ler.
"""

import json
import uuid
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.automations.decision import MAX_DECISION_NODES
from app.domain.automations.engine import AutomationEngine
from app.domain.automations.models import (
    Automation,
    AutomationDecision,
    AutomationRunStep,
    StepStatus,
    TriggerKind,
)
from app.domain.integration_alerts.models import IntegrationAlert
from app.domain.notifications.models import Notification
from app.domain.posts.models import Post
from app.domain.users.models import UserRole
from app.integrations.openrouter.types import LLMError, LLMResponse, Usage
from tests.integration.conftest import SeededUser, auth_header
from tests.integration.test_ai_copilot import ScriptedProvider
from tests.integration.test_automations import Cena, build_cena

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def cena(client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]) -> Cena:
    return await build_cena(client, make_user)


def _decisao(
    branch: str, *, confidence: float = 0.9, reasoning: str = "O prazo citado é de 5 dias."
) -> LLMResponse:
    return LLMResponse(
        content=json.dumps(
            {"branch": branch, "confidence": confidence, "reasoning": reasoning},
            ensure_ascii=False,
        ),
        usage=Usage(prompt_tokens=400, completion_tokens=60, cost_usd=0.002),
        model="fabricante-x/modelo-y",
        finish_reason="stop",
    )


class FailingProvider(ScriptedProvider):
    """Provider que não responde — o caso da regra 5."""

    async def complete(self, **kwargs: Any) -> LLMResponse:
        raise LLMError("modelo indisponível")


def _acao_de_decisao(
    *,
    branches: dict[str, list[int]],
    nomes: list[str] | None = None,
    default: str = "normal",
    min_confidence: float = 0.7,
    context_tools: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "action_kind": "llm_decision",
        "action_config": {
            "question": "Esta intimação exige resposta em até 5 dias?",
            "branches": nomes or list(branches),
            "default_branch": default,
            "min_confidence": min_confidence,
            "context_tools": context_tools or ["get_lawsuit"],
        },
        "branches": branches,
    }


async def _criar(
    client: AsyncClient, user: SeededUser, actions: list[dict[str, Any]]
) -> dict[str, Any]:
    resposta = await client.post(
        "/api/v1/automations",
        json={
            "name": f"Decisão {uuid.uuid4().hex[:8]}",
            "trigger_kind": TriggerKind.LAWSUIT_CREATED.value,
            "trigger_config": {},
            "actions": actions,
        },
        headers=auth_header(user),
    )
    return {"status": resposta.status_code, "body": resposta.json()}


async def _emitir(
    sessions: async_sessionmaker[AsyncSession],
    cena: Cena,
    provider: Any,
    payload: dict[str, Any] | None = None,
) -> uuid.UUID:
    from app.domain.ai.service import AiRunner

    async with sessions() as session, session.begin():
        await set_tenant_context(session, cena.user.tenant_id)
        engine = AutomationEngine(
            session,
            cena.user.tenant_id,
            ai_runner=AiRunner(session, cena.user.tenant_id, provider),
        )
        execucoes = await engine.emit(
            TriggerKind.LAWSUIT_CREATED.value, payload=payload or cena.payload
        )
        assert len(execucoes) == 1
        return execucoes[0].id


async def _decisoes(
    sessions: async_sessionmaker[AsyncSession], user: SeededUser
) -> list[AutomationDecision]:
    async with sessions() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        stmt = select(AutomationDecision).order_by(AutomationDecision.created_at)
        return list((await session.scalars(stmt)).all())


async def _passos(
    sessions: async_sessionmaker[AsyncSession], user: SeededUser, run_id: uuid.UUID
) -> list[AutomationRunStep]:
    async with sessions() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        stmt = (
            select(AutomationRunStep)
            .where(AutomationRunStep.run_id == run_id)
            .order_by(AutomationRunStep.position)
        )
        return list((await session.scalars(stmt)).all())


async def _tarefas(sessions: async_sessionmaker[AsyncSession], user: SeededUser) -> list[Post]:
    async with sessions() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        return list((await session.scalars(select(Post))).all())


async def _notificacoes(
    sessions: async_sessionmaker[AsyncSession], user: SeededUser
) -> list[Notification]:
    async with sessions() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        return list((await session.scalars(select(Notification))).all())


def _cenario_dois_ramos(cena: Cena) -> list[dict[str, Any]]:
    """Decisão na posição 0; ramo `urgente` na 1, ramo `normal` na 2."""
    return [
        _acao_de_decisao(branches={"urgente": [1], "normal": [2]}),
        {
            "action_kind": "create_task",
            "action_config": {"task_type_id": cena.task_type_id},
        },
        {"action_kind": "notify", "action_config": {"title": "Sem pressa"}},
    ]


# ------------------------------------------------------------------- decisão


async def test_decisao_escolhe_o_ramo_e_executa_so_as_acoes_dele(
    cena: Cena, client: AsyncClient, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    criada = await _criar(client, cena.user, _cenario_dois_ramos(cena))
    assert criada["status"] == 201, criada["body"]

    run_id = await _emitir(
        app_session_factory, cena, ScriptedProvider(script=[_decisao("urgente")])
    )

    passos = await _passos(app_session_factory, cena.user, run_id)
    assert [passo.status for passo in passos] == [
        StepStatus.DONE.value,  # a decisão
        StepStatus.DONE.value,  # o ramo escolhido
        StepStatus.SKIPPED.value,  # o ramo não escolhido
    ]
    assert passos[2].detail == {"branch": "normal", "chosen": "urgente"}
    assert len(await _tarefas(app_session_factory, cena.user)) == 1
    assert await _notificacoes(app_session_factory, cena.user) == []


async def test_ramo_inventado_cai_no_padrao_e_registra_a_anomalia(
    cena: Cena, client: AsyncClient, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 1: o modelo respondeu um ramo que não existe. Não dá para adivinhar o que
    ele quis dizer — vai para o padrão, e fica registrado que ele inventou."""
    await _criar(client, cena.user, _cenario_dois_ramos(cena))

    await _emitir(
        app_session_factory, cena, ScriptedProvider(script=[_decisao("emergencia_total")])
    )

    decisao = (await _decisoes(app_session_factory, cena.user))[0]
    assert decisao.chosen_branch == "normal"
    assert decisao.fell_back is True
    assert "fora da lista" in (decisao.fallback_reason or "")


async def test_confianca_baixa_cai_no_padrao_com_o_motivo(
    cena: Cena, client: AsyncClient, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 2: decidir com pouca certeza é pior que não decidir — o padrão é o caminho
    conservador que o escritório escolheu de antemão."""
    await _criar(client, cena.user, _cenario_dois_ramos(cena))

    await _emitir(
        app_session_factory,
        cena,
        ScriptedProvider(script=[_decisao("urgente", confidence=0.4)]),
    )

    decisao = (await _decisoes(app_session_factory, cena.user))[0]
    assert decisao.chosen_branch == "normal"
    assert decisao.fell_back is True
    assert "0.40" in (decisao.fallback_reason or "")
    assert float(decisao.confidence or 0) == 0.4


async def test_contexto_usa_so_ferramentas_de_leitura(
    cena: Cena, client: AsyncClient, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 3, o teste que a spec destaca: o nó de decisão NUNCA escreve. Nenhuma
    ferramenta de escrita é sequer oferecida ao modelo."""
    await _criar(
        client,
        cena.user,
        [
            _acao_de_decisao(
                branches={"urgente": [1], "normal": [2]},
                context_tools=["get_lawsuit", "create_customer", "update_lawsuit"],
            ),
            {"action_kind": "create_task", "action_config": {"task_type_id": cena.task_type_id}},
            {"action_kind": "notify", "action_config": {"title": "Sem pressa"}},
        ],
    )
    provider = ScriptedProvider(script=[_decisao("normal")])

    await _emitir(app_session_factory, cena, provider)

    oferecidas = provider.tools_offered[0]
    assert "get_lawsuit" in oferecidas
    assert not (
        {"create_customer", "update_lawsuit"} & set(oferecidas)
    ), "ferramenta de escrita não pode chegar ao nó de decisão nem por configuração"


async def test_raciocinio_e_sempre_gravado(
    cena: Cena, client: AsyncClient, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 4: automação que decide sem explicar não é auditável."""
    await _criar(client, cena.user, _cenario_dois_ramos(cena))

    await _emitir(
        app_session_factory,
        cena,
        ScriptedProvider(script=[_decisao("urgente", reasoning="O ofício fala em 5 dias.")]),
    )

    decisao = (await _decisoes(app_session_factory, cena.user))[0]
    assert decisao.reasoning == "O ofício fala em 5 dias."
    assert decisao.model == "fabricante-x/modelo-y"
    assert decisao.tokens_used == 460


async def test_decisao_sem_raciocinio_nao_vale_mais_que_o_padrao(
    cena: Cena, client: AsyncClient, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 4 levada a sério: o modelo escolheu um ramo válido, mas não explicou."""
    await _criar(client, cena.user, _cenario_dois_ramos(cena))
    resposta = LLMResponse(
        content=json.dumps({"branch": "urgente", "confidence": 0.99}),
        usage=Usage(prompt_tokens=10, completion_tokens=5),
        model="fabricante-x/modelo-y",
        finish_reason="stop",
    )

    await _emitir(app_session_factory, cena, ScriptedProvider(script=[resposta]))

    decisao = (await _decisoes(app_session_factory, cena.user))[0]
    assert decisao.chosen_branch == "normal"
    assert decisao.fell_back is True
    assert "auditável" in (decisao.fallback_reason or "")


# ------------------------------------------------------------------ fallback


async def test_falha_do_llm_cai_no_padrao_e_a_automacao_continua(
    cena: Cena, client: AsyncClient, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 5, a mais importante da spec: um escritório não pode perder prazo porque um
    provider de modelo ficou fora do ar."""
    await _criar(client, cena.user, _cenario_dois_ramos(cena))

    run_id = await _emitir(app_session_factory, cena, FailingProvider())

    passos = await _passos(app_session_factory, cena.user, run_id)
    assert [passo.status for passo in passos] == [
        StepStatus.DONE.value,
        StepStatus.SKIPPED.value,
        StepStatus.DONE.value,
    ], "o ramo padrão rodou e a automação terminou"
    decisao = (await _decisoes(app_session_factory, cena.user))[0]
    assert decisao.fell_back is True
    assert "não respondeu" in (decisao.fallback_reason or "")
    assert len(await _notificacoes(app_session_factory, cena.user)) == 1


async def test_sem_chave_de_ia_a_automacao_continua_funcionando(
    cena: Cena, client: AsyncClient, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Mesma regra por outro caminho: servidor sem `OPENROUTER_API_KEY`."""
    from app.integrations.openrouter.types import LLMNotConfiguredError

    class SemChave(ScriptedProvider):
        is_configured = False

        async def complete(self, **kwargs: Any) -> LLMResponse:
            raise LLMNotConfiguredError("OPENROUTER_API_KEY não configurada.")

    await _criar(client, cena.user, _cenario_dois_ramos(cena))

    run_id = await _emitir(app_session_factory, cena, SemChave())

    passos = await _passos(app_session_factory, cena.user, run_id)
    assert passos[-1].status == StepStatus.DONE.value
    assert (await _decisoes(app_session_factory, cena.user))[0].fell_back is True


async def test_orcamento_estourado_usa_o_padrao_sem_chamar_o_modelo(
    cena: Cena, client: AsyncClient, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 6: pagar para descobrir que não podia pagar seria a pior ordem possível."""
    criada = await _criar(client, cena.user, _cenario_dois_ramos(cena))
    automation_id = uuid.UUID(criada["body"]["id"])
    resposta = await client.put(
        f"/api/v1/automations/{automation_id}/ai-budget",
        json={"monthly_ai_budget_usd": "1.00"},
        headers=auth_header(cena.user),
    )
    assert resposta.status_code == 200, resposta.text

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, cena.user.tenant_id)
        automation = await session.get(Automation, automation_id)
        assert automation is not None
        automation.current_month_spend_usd = Decimal("1.50")
        from datetime import date

        hoje = date.today()
        automation.spend_month = date(hoje.year, hoje.month, 1)

    provider = ScriptedProvider(script=[_decisao("urgente")])
    await _emitir(app_session_factory, cena, provider)

    assert provider.prompts == [], "com o orçamento no fim, nem chega a chamar"
    decisao = (await _decisoes(app_session_factory, cena.user))[0]
    assert decisao.chosen_branch == "normal"
    assert "orçamento" in (decisao.fallback_reason or "").lower()

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, cena.user.tenant_id)
        alertas = list(
            (
                await session.scalars(
                    select(IntegrationAlert).where(IntegrationAlert.code == "ai_budget_exhausted")
                )
            ).all()
        )
    assert len(alertas) == 1


async def test_gasto_da_decisao_entra_no_contador_da_automacao(
    cena: Cena, client: AsyncClient, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 12: toda decisão registra tokens e custo — sem isso o teto não teria como
    ser respeitado."""
    criada = await _criar(client, cena.user, _cenario_dois_ramos(cena))

    await _emitir(app_session_factory, cena, ScriptedProvider(script=[_decisao("urgente")]))

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, cena.user.tenant_id)
        automation = await session.get(Automation, uuid.UUID(criada["body"]["id"]))
        assert automation is not None
        assert automation.current_month_spend_usd == Decimal("0.002")
    assert (await _decisoes(app_session_factory, cena.user))[0].cost_usd == Decimal("0.002000")


# ------------------------------------------------------------------ limites


async def test_quarto_no_de_decisao_e_recusado(cena: Cena, client: AsyncClient) -> None:
    """Regra 7: mais que três é regra de negócio disfarçada de IA — e cada nó é uma
    chamada paga em toda execução."""
    acoes = [
        _acao_de_decisao(branches={"urgente": [], "normal": []})
        for _ in range(MAX_DECISION_NODES + 1)
    ]

    criada = await _criar(client, cena.user, acoes)

    assert criada["status"] == 422
    assert "no máximo 3" in criada["body"]["detail"]


async def test_ramo_aninhado_e_recusado(cena: Cena, client: AsyncClient) -> None:
    """Regra 9: ramificação aninhada vira um fluxograma que ninguém revisa — e automação
    que ninguém revisa é automação que ninguém desliga quando erra."""
    criada = await _criar(
        client,
        cena.user,
        [
            _acao_de_decisao(branches={"urgente": [1], "normal": [2]}),
            _acao_de_decisao(branches={"urgente": [], "normal": []}),
            {"action_kind": "notify", "action_config": {"title": "Sem pressa"}},
        ],
    )

    assert criada["status"] == 422
    assert "aninhada" in criada["body"]["detail"]


async def test_ramo_padrao_precisa_existir(cena: Cena, client: AsyncClient) -> None:
    """Sem padrão válido não há caminho de fallback, e a regra 5 deixa de poder ser
    cumprida: a automação pararia na primeira falha de IA."""
    acao = _acao_de_decisao(branches={"urgente": [], "normal": []}, default="inexistente")

    criada = await _criar(client, cena.user, [acao])

    assert criada["status"] == 422
    assert "ramo padrão" in criada["body"]["detail"]


# --------------------------------------------------------------- simulação


async def test_simulacao_decide_mas_nao_executa_acoes(
    cena: Cena, client: AsyncClient, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 10: a decisão acontece de verdade — é o ponto, quem escreve a automação
    precisa ver o modelo escolher com o contexto real — e nenhuma ação roda."""
    criada = await _criar(client, cena.user, _cenario_dois_ramos(cena))
    from app.domain.ai.router import get_llm_provider
    from app.main import app

    app.dependency_overrides[get_llm_provider] = lambda: ScriptedProvider(
        script=[_decisao("urgente")]
    )
    try:
        resposta = await client.post(
            f"/api/v1/automations/{criada['body']['id']}/decisions/simulate",
            json={"payload": cena.payload},
            headers=auth_header(cena.user),
        )
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["chosen_branch"] == "urgente"
    assert corpo["reasoning"]
    assert corpo["executed"] is False
    assert await _tarefas(app_session_factory, cena.user) == []
    assert await _decisoes(app_session_factory, cena.user) == []


async def test_decisoes_de_outro_escritorio_nao_aparecem(
    cena: Cena, client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    intruso = await make_user(role=UserRole.GESTOR)
    criada = await _criar(client, cena.user, _cenario_dois_ramos(cena))

    resposta = await client.get(
        f"/api/v1/automations/{criada['body']['id']}/decisions", headers=auth_header(intruso)
    )

    assert resposta.status_code == 404
