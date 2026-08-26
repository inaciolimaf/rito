"""IA analítica (spec 089) — text-to-SQL guardrailed, next-best-action e insights.

O foco dos testes é a quarta camada de guardrail (a conexão somente-leitura, que não
depende de análise de texto nenhuma), o registro das tentativas e o fato de que a
recomendação por processo é **decidida por regra**, não por modelo.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.ai.analytics import DISMISS_COOLDOWN_DAYS, AnalyticsService
from app.domain.ai.models import AiInsight, AiSqlQuery
from app.domain.ai.service import AiRunner
from app.domain.users.models import FinancialAccess, User, UserRole
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
from tests.integration.test_posts import _create_post, _create_task_type


def _sql(sql: str) -> LLMResponse:
    return LLMResponse(
        content=sql,
        usage=Usage(prompt_tokens=200, completion_tokens=40),
        model="fabricante-x/modelo-y",
        finish_reason="stop",
    )


@pytest.fixture(autouse=True)
def _reset_overrides() -> Any:
    from app.domain.ai.router import get_llm_provider
    from app.main import app

    yield
    app.dependency_overrides.pop(get_llm_provider, None)


async def _ask(
    client: AsyncClient, user: SeededUser, question: str, confirm_sql: str | None = None
) -> Any:
    return await client.post(
        "/api/v1/ai/analytics/ask",
        json={"question": question, "confirm_sql": confirm_sql},
        headers=auth_header(user),
    )


async def _lawsuit(client: AsyncClient, user: SeededUser) -> tuple[str, str, str]:
    """Processo com cliente e tipo de tarefa — a base dos sinais do next-best-action."""
    headers = _auth_header(user)
    type_id, _group = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    customer_id = await _create_customer(client, headers, "Cliente da Análise")
    lawsuit = await _create_lawsuit(
        client,
        headers,
        user_id=str(user.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
        parties=[{"customer_id": customer_id, "pole": "ATIVO", "is_client": True}],
    )
    task_type_id = await _create_task_type(client, headers)
    return str(lawsuit["id"]), customer_id, task_type_id


async def test_pergunta_simples_gera_sql_valido_e_so_roda_depois_de_confirmar(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 3: a primeira chamada mostra o SQL; nada é executado sem a segunda."""
    # GESTOR porque o cenário cria taxonomia (grupo/tipo/etapa); pela hierarquia da
    # spec 005, ele também satisfaz o ADMINISTRADOR que o text-to-SQL exige.
    user = await make_user(role=UserRole.GESTOR)
    await _lawsuit(client, user)
    _use(ScriptedProvider(script=[_sql("SELECT month, lawsuits FROM ai_allowed_metrics")]))

    proposta = await _ask(client, user, "quantos processos por mês?")

    assert proposta.status_code == 200, proposta.text
    assert proposta.json()["executed"] is False
    assert proposta.json()["sql"].startswith("SELECT")
    assert proposta.json()["rows"] == []

    executado = await _ask(client, user, "quantos processos por mês?", proposta.json()["sql"])

    assert executado.status_code == 200, executado.text
    assert executado.json()["executed"] is True
    assert "month" in executado.json()["columns"]
    assert executado.json()["summary"]


async def test_tentativa_rejeitada_e_registrada_com_o_motivo(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 8 do §5: a tentativa recusada é a que mais interessa auditar."""
    user = await make_user(role=UserRole.ADMINISTRADOR)
    _use(ScriptedProvider(script=[_sql("SELECT name, email FROM customers")]))

    resposta = await _ask(client, user, "liste os e-mails dos clientes")

    assert resposta.status_code == 422
    assert "fora do catálogo" in resposta.json()["detail"]
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        registro = (await session.scalars(select(AiSqlQuery))).one()
    assert registro.was_allowed is False
    assert registro.rejection_reason is not None
    assert "customers" in registro.generated_sql


async def test_conexao_somente_leitura_barra_escrita_mesmo_com_sql_aprovado(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A quarta camada (§5, item 4), testada sozinha: mesmo que as três de análise
    falhassem, a transação não consegue escrever."""
    user = await make_user(role=UserRole.GESTOR)
    _use(ScriptedProvider())

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        service = AnalyticsService(
            session=session,
            tenant_id=user.tenant_id,
            runner=AiRunner(session, user.tenant_id, ScriptedProvider()),
        )
        actor = await session.get(User, user.user_id)
        assert actor is not None

        from app.domain.ai.sql_guard import CheckedSql

        # SQL que o guardrail JAMAIS deixaria passar, injetado direto na execução.
        malicioso = CheckedSql(
            sql="INSERT INTO ai_insights (tenant_id, kind, severity, title, body) "
            f"VALUES ('{user.tenant_id}', 'x', 'info', 'x', 'x')",
            relations=["ai_insights"],
            touches_financial=False,
        )
        with pytest.raises(Exception) as exc:
            await service.run_sql(user=actor, question="tentativa", checked=malicioso)
        assert "read-only" in str(exc.value).lower() or "somente leitura" in str(exc.value).lower()

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        assert list((await session.scalars(select(AiInsight))).all()) == []


async def test_ambiguidade_pede_esclarecimento_em_vez_de_chutar(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 1: SQL chutado sobre pergunta ambígua responde com confiança algo errado."""
    user = await make_user(role=UserRole.ADMINISTRADOR)
    _use(
        ScriptedProvider(script=[_sql("PRECISO_DE_ESCLARECIMENTO: você quer por mês ou por ano?")])
    )

    resposta = await _ask(client, user, "como está o desempenho?")

    assert resposta.status_code == 422
    assert resposta.json()["clarification"] == "você quer por mês ou por ano?"


async def test_metrica_financeira_exige_acesso_financeiro(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 5: ser ADMINISTRADOR não dá acesso a dinheiro."""
    sem_financeiro = await make_user(
        role=UserRole.ADMINISTRADOR, financial_access=FinancialAccess.NONE
    )
    com_financeiro = await make_user(
        role=UserRole.ADMINISTRADOR, financial_access=FinancialAccess.READ_ONLY
    )
    consulta = "SELECT sum(total_case_value) AS total FROM ai_allowed_metrics"

    _use(ScriptedProvider(script=[_sql(consulta)]))
    negado = await _ask(client, sem_financeiro, "qual o valor da carteira?")
    _use(ScriptedProvider(script=[_sql(consulta)]))
    permitido = await _ask(client, com_financeiro, "qual o valor da carteira?")

    assert negado.status_code == 422
    assert "acesso" in negado.json()["detail"]
    assert permitido.status_code == 200
    assert permitido.json()["touches_financial"] is True


async def test_colaborador_nao_usa_text_to_sql(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 5, primeira metade."""
    colaborador = await make_user(role=UserRole.COLABORADOR)
    _use(ScriptedProvider(script=[_sql("SELECT month FROM ai_allowed_metrics")]))

    resposta = await _ask(client, colaborador, "quantos processos?")

    assert resposta.status_code == 403


async def test_next_best_action_considera_os_sinais_do_processo(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 6: a recomendação é calculada por regra — igual toda vez que os dados
    forem iguais, e sem custo por consulta."""
    user = await make_user(role=UserRole.GESTOR)
    lawsuit_id, _customer_id, task_type_id = await _lawsuit(client, user)
    _use(ScriptedProvider())

    # Sem tarefa nenhuma: o processo está sem dono do dia a dia.
    sem_tarefa = await client.get(
        f"/api/v1/lawsuits/{lawsuit_id}/next-best-action", headers=auth_header(user)
    )
    assert sem_tarefa.status_code == 200, sem_tarefa.text
    assert sem_tarefa.json()["action"] == "Definir a próxima tarefa"
    assert sem_tarefa.json()["suggested_tool"] == "create_task"

    # Com uma tarefa vencida, o prazo passa na frente de tudo.
    await _create_post(
        client,
        _auth_header(user),
        lawsuit_id=lawsuit_id,
        task_type_id=task_type_id,
        user_ids=[str(user.user_id)],
        deadline_date=(date.today() - timedelta(days=2)).isoformat(),
        scheduled_date=(date.today() - timedelta(days=2)).isoformat(),
    )
    com_atraso = await client.get(
        f"/api/v1/lawsuits/{lawsuit_id}/next-best-action", headers=auth_header(user)
    )

    assert com_atraso.json()["action"] == "Concluir as tarefas em atraso"
    assert com_atraso.json()["signals"]["overdue_tasks"] == 1
    # Regra 7: a sugestão aponta a ferramenta, mas quem cria a tarefa é o fluxo da 084.
    assert com_atraso.json()["signals"]["open_tasks"] == 1


async def test_insights_apontam_registro_e_nao_repetem(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regras 9 e 12: cada insight aponta o registro que o originou, e rodar o job duas
    vezes não duplica o aviso."""
    user = await make_user(role=UserRole.GESTOR)
    lawsuit_id, _customer_id, task_type_id = await _lawsuit(client, user)
    await _create_post(
        client,
        _auth_header(user),
        lawsuit_id=lawsuit_id,
        task_type_id=task_type_id,
        user_ids=[str(user.user_id)],
        deadline_date=(date.today() + timedelta(days=1)).isoformat(),
        scheduled_date=(date.today() + timedelta(days=1)).isoformat(),
    )
    _use(ScriptedProvider())

    primeiro = await client.post("/api/v1/ai/insights/refresh", headers=auth_header(user))
    segundo = await client.post("/api/v1/ai/insights/refresh", headers=auth_header(user))

    assert primeiro.json()["created"] >= 1
    assert segundo.json()["created"] == 0, "o mesmo aviso não vira dois"

    listagem = await client.get(
        "/api/v1/ai/insights", params={"kind": "deadline_risk"}, headers=auth_header(user)
    )
    itens = listagem.json()["items"]
    assert itens[0]["subject_type"] == "lawsuit"
    assert itens[0]["subject_id"] == lawsuit_id
    assert itens[0]["severity"] == "critical"


async def test_insight_dispensado_nao_volta_por_trinta_dias(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 10."""
    user = await make_user(role=UserRole.GESTOR)
    lawsuit_id, _customer_id, task_type_id = await _lawsuit(client, user)
    await _create_post(
        client,
        _auth_header(user),
        lawsuit_id=lawsuit_id,
        task_type_id=task_type_id,
        user_ids=[str(user.user_id)],
        deadline_date=(date.today() + timedelta(days=1)).isoformat(),
        scheduled_date=(date.today() + timedelta(days=1)).isoformat(),
    )
    _use(ScriptedProvider())
    await client.post("/api/v1/ai/insights/refresh", headers=auth_header(user))
    listagem = await client.get("/api/v1/ai/insights", headers=auth_header(user))
    insight_id = listagem.json()["items"][0]["id"]

    dispensado = await client.post(
        f"/api/v1/ai/insights/{insight_id}/dismiss", headers=auth_header(user)
    )
    assert dispensado.status_code == 200
    novamente = await client.post("/api/v1/ai/insights/refresh", headers=auth_header(user))
    assert novamente.json()["created"] == 0

    # Passados os 30 dias, o aviso pode voltar — o assunto não some para sempre.
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        await session.execute(
            text("UPDATE ai_insights SET dismissed_at = :quando WHERE id = :id"),
            {
                "quando": datetime.now(UTC) - timedelta(days=DISMISS_COOLDOWN_DAYS + 1),
                "id": uuid.UUID(insight_id),
            },
        )
        service = AnalyticsService(
            session=session,
            tenant_id=user.tenant_id,
            runner=AiRunner(session, user.tenant_id, ScriptedProvider()),
        )
        criados = await service.refresh_insights()

    assert criados >= 1
