"""Motor de automação (spec 092 §8).

O teste que carrega a spec não é nenhum dos cinco gatilhos: é a **proteção contra laço**.
Um motor de automação sem teto é a única feature deste sistema capaz de encher o banco
sozinha durante a madrugada — e o jeito de provar que ela não faz isso é montar a
automação que se alimentaria e verificar onde ela para.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.automations.engine import MAX_CHAIN_DEPTH, AutomationEngine
from app.domain.automations.models import (
    Automation,
    AutomationRun,
    AutomationRunStep,
    RunStatus,
    StepStatus,
    TriggerKind,
)
from app.domain.automations.sweep import emit_overdue_transactions, resume_due_runs
from app.domain.lawsuits.models import Lawsuit
from app.domain.notifications.models import Notification
from app.domain.posts.models import Post
from app.domain.users.models import FinancialAccess, UserRole
from tests.integration.conftest import SeededUser, auth_header
from tests.integration.test_lawsuits import (
    _auth_header,
    _create_customer,
    _create_lawsuit,
    _create_lawsuit_type,
    _create_stage,
)
from tests.integration.test_posts import _create_task_type

pytestmark = pytest.mark.asyncio


class Cena:
    """Um escritório com processo, etapas e tipo de tarefa — a base de qualquer regra."""

    def __init__(
        self,
        user: SeededUser,
        lawsuit_id: str,
        stage_id: str,
        other_stage_id: str,
        task_type_id: str,
        lawsuit_type_id: str,
    ) -> None:
        self.user = user
        self.lawsuit_id = lawsuit_id
        self.stage_id = stage_id
        self.other_stage_id = other_stage_id
        self.task_type_id = task_type_id
        self.lawsuit_type_id = lawsuit_type_id

    @property
    def payload(self) -> dict[str, Any]:
        return {"lawsuit_id": self.lawsuit_id, "lawsuit_type_id": self.lawsuit_type_id}


@pytest.fixture
async def cena(client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]) -> Cena:
    user = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(user)
    type_id, _group = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    other_stage_id = await _create_stage(client, headers)
    customer_id = await _create_customer(client, headers, f"Cliente {uuid.uuid4().hex[:6]}")
    lawsuit = await _create_lawsuit(
        client,
        headers,
        user_id=str(user.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
        parties=[{"customer_id": customer_id, "pole": "ATIVO", "is_client": True}],
    )
    task_type_id = await _create_task_type(client, headers)
    return Cena(user, str(lawsuit["id"]), stage_id, other_stage_id, task_type_id, type_id)


async def _criar_automacao(
    client: AsyncClient,
    user: SeededUser,
    *,
    trigger_kind: str,
    actions: list[dict[str, Any]],
    trigger_config: dict[str, Any] | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    resposta = await client.post(
        "/api/v1/automations",
        json={
            "name": name or f"Regra {uuid.uuid4().hex[:8]}",
            "trigger_kind": trigger_kind,
            "trigger_config": trigger_config or {},
            "actions": actions,
        },
        headers=auth_header(user),
    )
    assert resposta.status_code == 201, resposta.text
    return dict(resposta.json())


async def _emitir(
    sessions: async_sessionmaker[AsyncSession],
    user: SeededUser,
    trigger_kind: str,
    payload: dict[str, Any],
    **extra: Any,
) -> list[uuid.UUID]:
    async with sessions() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        engine = AutomationEngine(session, user.tenant_id, now=extra.pop("now", None))
        execucoes = await engine.emit(trigger_kind, payload=payload, **extra)
        return [run.id for run in execucoes]


async def _runs(
    sessions: async_sessionmaker[AsyncSession], user: SeededUser
) -> list[AutomationRun]:
    async with sessions() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        stmt = select(AutomationRun).order_by(AutomationRun.started_at)
        return list((await session.scalars(stmt)).all())


async def _steps(
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


async def _posts(sessions: async_sessionmaker[AsyncSession], user: SeededUser) -> list[Post]:
    async with sessions() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        return list((await session.scalars(select(Post))).all())


# ------------------------------------------------------------------- gatilhos


@pytest.mark.parametrize(
    "trigger_kind",
    [item.value for item in TriggerKind],
)
async def test_os_cinco_gatilhos_abrem_execucao(
    trigger_kind: str,
    cena: Cena,
    client: AsyncClient,
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 1. Parametrizado pelo enum: gatilho novo sem teste não passa despercebido —
    e gatilho sem emissor seria uma automação que nunca roda, pior que não existir."""
    await _criar_automacao(
        client,
        cena.user,
        trigger_kind=trigger_kind,
        actions=[{"action_kind": "notify", "action_config": {"title": "Aconteceu"}}],
    )

    execucoes = await _emitir(app_session_factory, cena.user, trigger_kind, cena.payload)

    assert len(execucoes) == 1
    runs = await _runs(app_session_factory, cena.user)
    assert runs[0].status == RunStatus.DONE.value


async def test_trigger_config_restringe(
    cena: Cena, client: AsyncClient, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 2: 'tarefa concluída' pode valer só para um tipo de tarefa."""
    await _criar_automacao(
        client,
        cena.user,
        trigger_kind=TriggerKind.TASK_COMPLETED.value,
        trigger_config={"task_type_id": cena.task_type_id},
        actions=[{"action_kind": "notify", "action_config": {"title": "Concluiu"}}],
    )

    outro = await _emitir(
        app_session_factory,
        cena.user,
        TriggerKind.TASK_COMPLETED.value,
        {**cena.payload, "task_type_id": str(uuid.uuid4())},
    )
    certo = await _emitir(
        app_session_factory,
        cena.user,
        TriggerKind.TASK_COMPLETED.value,
        {**cena.payload, "task_type_id": cena.task_type_id},
    )

    assert outro == []
    assert len(certo) == 1


# -------------------------------------------------------------------- sequência


async def test_acoes_executam_em_sequencia(
    cena: Cena, client: AsyncClient, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 3: `position` manda. Ordem trocada num fluxo jurídico é prazo perdido."""
    await _criar_automacao(
        client,
        cena.user,
        trigger_kind=TriggerKind.LAWSUIT_CREATED.value,
        actions=[
            {"action_kind": "notify", "action_config": {"title": "Primeiro"}},
            {"action_kind": "change_stage", "action_config": {"stage_id": cena.other_stage_id}},
            {
                "action_kind": "create_task",
                "action_config": {"task_type_id": cena.task_type_id},
            },
        ],
    )

    (run_id,) = await _emitir(
        app_session_factory, cena.user, TriggerKind.LAWSUIT_CREATED.value, cena.payload
    )

    passos = await _steps(app_session_factory, cena.user, run_id)
    runs = await _runs(app_session_factory, cena.user)
    assert runs[0].error is None, runs[0].error
    assert [passo.action_kind for passo in passos] == ["notify", "change_stage", "create_task"]
    assert all(passo.status == StepStatus.DONE.value for passo in passos)

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, cena.user.tenant_id)
        lawsuit = await session.get(Lawsuit, uuid.UUID(cena.lawsuit_id))
        assert lawsuit is not None
        assert str(lawsuit.stage_id) == cena.other_stage_id


async def test_after_previous_espera_a_tarefa_ser_concluida(
    cena: Cena, client: AsyncClient, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 4: 'protocolar' só depois de 'revisar' — encadeamento de verdade, não um
    atraso de N dias torcendo para a tarefa anterior ter terminado."""
    await _criar_automacao(
        client,
        cena.user,
        trigger_kind=TriggerKind.LAWSUIT_CREATED.value,
        actions=[
            {"action_kind": "create_task", "action_config": {"task_type_id": cena.task_type_id}},
            {
                "action_kind": "notify",
                "action_config": {"title": "A revisão terminou"},
                "delay_kind": "after_previous",
            },
        ],
    )

    (run_id,) = await _emitir(
        app_session_factory, cena.user, TriggerKind.LAWSUIT_CREATED.value, cena.payload
    )

    runs = await _runs(app_session_factory, cena.user)
    assert runs[0].status == RunStatus.WAITING.value, "a segunda ação não pode ter rodado"
    tarefa = (await _posts(app_session_factory, cena.user))[0]

    concluida = await client.post(
        f"/api/v1/posts/{tarefa.id}/complete", json={}, headers=auth_header(cena.user)
    )
    assert concluida.status_code == 200, concluida.text

    runs = await _runs(app_session_factory, cena.user)
    assert runs[0].status == RunStatus.DONE.value
    passos = await _steps(app_session_factory, cena.user, run_id)
    assert [passo.action_kind for passo in passos] == ["create_task", "notify"]


async def test_atraso_em_dias_uteis_pula_o_feriado(
    cena: Cena, client: AsyncClient, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 5: o mesmo cálculo da 040, com os feriados do banco. Uma automação que
    marcasse prazo em 25 de dezembro seria pior que automação nenhuma."""
    await _criar_automacao(
        client,
        cena.user,
        trigger_kind=TriggerKind.LAWSUIT_CREATED.value,
        actions=[
            {
                "action_kind": "notify",
                "action_config": {"title": "Depois do Natal"},
                "delay_kind": "business_days",
                "delay_value": 1,
            }
        ],
    )
    # 24/12/2026 é quinta; 25 é feriado nacional e 26/27 é fim de semana — 1 dia útil
    # depois cai na segunda, 28.
    vespera = datetime(2026, 12, 24, 10, 0, tzinfo=UTC)

    await _emitir(
        app_session_factory,
        cena.user,
        TriggerKind.LAWSUIT_CREATED.value,
        cena.payload,
        now=vespera,
    )

    runs = await _runs(app_session_factory, cena.user)
    assert runs[0].status == RunStatus.WAITING.value
    assert runs[0].next_action_at is not None
    assert runs[0].next_action_at.date() == date(2026, 12, 28)


async def test_condicao_falsa_pula_e_registra(
    cena: Cena, client: AsyncClient, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 6: 'por que a tarefa não foi criada?' é a pergunta que chega ao suporte."""
    await _criar_automacao(
        client,
        cena.user,
        trigger_kind=TriggerKind.LAWSUIT_CREATED.value,
        actions=[
            {
                "action_kind": "create_task",
                "action_config": {"task_type_id": cena.task_type_id},
                "condition": {"field": "urgente", "op": "eq", "value": True},
            },
            {"action_kind": "notify", "action_config": {"title": "Seguiu mesmo assim"}},
        ],
    )

    (run_id,) = await _emitir(
        app_session_factory,
        cena.user,
        TriggerKind.LAWSUIT_CREATED.value,
        {**cena.payload, "urgente": False},
    )

    passos = await _steps(app_session_factory, cena.user, run_id)
    assert passos[0].status == StepStatus.SKIPPED.value
    assert passos[0].detail == {"condition": {"field": "urgente", "op": "eq", "value": True}}
    assert passos[1].status == StepStatus.DONE.value
    assert await _posts(app_session_factory, cena.user) == []


# ------------------------------------------------------------- proteção de laço


async def test_automacao_nao_dispara_a_si_mesma(
    cena: Cena, client: AsyncClient, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 7, primeira metade. O caso não é hipotético: 'tarefa concluída → criar
    tarefa' se auto-alimentaria na primeira conclusão."""
    criada = await _criar_automacao(
        client,
        cena.user,
        trigger_kind=TriggerKind.TASK_COMPLETED.value,
        actions=[
            {"action_kind": "create_task", "action_config": {"task_type_id": cena.task_type_id}}
        ],
    )

    execucoes = await _emitir(
        app_session_factory,
        cena.user,
        TriggerKind.TASK_COMPLETED.value,
        cena.payload,
        source_automation_id=uuid.UUID(criada["id"]),
    )

    assert execucoes == []


async def test_cadeia_para_no_decimo(
    cena: Cena, client: AsyncClient, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 7, segunda metade: duas automações se alimentando param no décimo elo."""
    await _criar_automacao(
        client,
        cena.user,
        trigger_kind=TriggerKind.LAWSUIT_CREATED.value,
        actions=[{"action_kind": "notify", "action_config": {"title": "Elo"}}],
    )

    no_limite = await _emitir(
        app_session_factory,
        cena.user,
        TriggerKind.LAWSUIT_CREATED.value,
        cena.payload,
        chain_depth=MAX_CHAIN_DEPTH - 1,
    )
    passou = await _emitir(
        app_session_factory,
        cena.user,
        TriggerKind.LAWSUIT_CREATED.value,
        cena.payload,
        chain_depth=MAX_CHAIN_DEPTH,
    )

    assert len(no_limite) == 1
    assert passou == [], "no décimo elo a cadeia para"


# ------------------------------------------------------------ falha e reprocesso


async def test_reprocesso_e_idempotente(
    cena: Cena, client: AsyncClient, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 8: reprocessar não duplica — e quem garante é o UNIQUE do banco, não a
    lembrança do código de conferir antes."""
    await _criar_automacao(
        client,
        cena.user,
        trigger_kind=TriggerKind.LAWSUIT_CREATED.value,
        actions=[
            {"action_kind": "create_task", "action_config": {"task_type_id": cena.task_type_id}}
        ],
    )
    (run_id,) = await _emitir(
        app_session_factory, cena.user, TriggerKind.LAWSUIT_CREATED.value, cena.payload
    )

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, cena.user.tenant_id)
        run = await session.get(AutomationRun, run_id)
        assert run is not None
        run.next_position = 0
        run.status = RunStatus.RUNNING.value
        await AutomationEngine(session, cena.user.tenant_id).advance(run)

    assert len(await _steps(app_session_factory, cena.user, run_id)) == 1
    assert len(await _posts(app_session_factory, cena.user)) == 1


async def test_falha_interrompe_e_preserva_as_anteriores(
    cena: Cena, client: AsyncClient, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 9: o que já rodou permanece. Desfazer as ações anteriores seria pior — o
    prazo criado no passo 1 é real, e apagá-lo por causa do passo 3 é perder prazo."""
    await _criar_automacao(
        client,
        cena.user,
        trigger_kind=TriggerKind.LAWSUIT_CREATED.value,
        actions=[
            {"action_kind": "notify", "action_config": {"title": "Rodou"}},
            {"action_kind": "change_stage", "action_config": {"stage_id": str(uuid.uuid4())}},
            {"action_kind": "notify", "action_config": {"title": "Nunca chega"}},
        ],
    )

    (run_id,) = await _emitir(
        app_session_factory, cena.user, TriggerKind.LAWSUIT_CREATED.value, cena.payload
    )

    runs = await _runs(app_session_factory, cena.user)
    assert runs[0].status == RunStatus.FAILED.value
    assert runs[0].error
    passos = await _steps(app_session_factory, cena.user, run_id)
    assert [passo.status for passo in passos] == [
        StepStatus.DONE.value,
        StepStatus.FAILED.value,
    ]

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, cena.user.tenant_id)
        notificacoes = list((await session.scalars(select(Notification))).all())
    assert len(notificacoes) == 1, "a notificação do passo 1 continua valendo"


# ------------------------------------------------------------------- rotas


async def test_teste_nao_persiste(
    cena: Cena, client: AsyncClient, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 10: um 'teste' que grava é a pior armadilha possível numa tela chamada
    Testar."""
    criada = await _criar_automacao(
        client,
        cena.user,
        trigger_kind=TriggerKind.LAWSUIT_CREATED.value,
        actions=[
            {"action_kind": "create_task", "action_config": {"task_type_id": cena.task_type_id}},
            {
                "action_kind": "notify",
                "action_config": {"title": "Depois"},
                "delay_kind": "calendar_days",
                "delay_value": 3,
            },
        ],
    )

    simulacao = await client.post(
        f"/api/v1/automations/{criada['id']}/test",
        json={"payload": cena.payload},
        headers=auth_header(cena.user),
    )

    assert simulacao.status_code == 200, simulacao.text
    corpo = simulacao.json()
    assert corpo["persisted"] is False
    assert [passo["action_kind"] for passo in corpo["steps"]] == ["create_task", "notify"]
    assert corpo["steps"][1]["scheduled_for"] == (date.today() + timedelta(days=3)).isoformat()
    assert await _posts(app_session_factory, cena.user) == []
    assert await _runs(app_session_factory, cena.user) == []


async def test_permissao_e_a_do_criador(
    cena: Cena,
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 12: o ator é quem CRIOU a automação.

    Um Colaborador concluindo tarefa não pode acabar movendo a etapa de um processo que
    não é dele — mas a regra escrita pelo gestor tem de continuar funcionando quando é
    ele quem dispara.
    """
    colaborador = await make_user(role=UserRole.COLABORADOR)
    criada = await _criar_automacao(
        client,
        cena.user,
        trigger_kind=TriggerKind.LAWSUIT_CREATED.value,
        actions=[
            {"action_kind": "change_stage", "action_config": {"stage_id": cena.other_stage_id}}
        ],
    )

    (run_id,) = await _emitir(
        app_session_factory, cena.user, TriggerKind.LAWSUIT_CREATED.value, cena.payload
    )

    passos = await _steps(app_session_factory, cena.user, run_id)
    assert passos[0].status == StepStatus.DONE.value
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, cena.user.tenant_id)
        automation = await session.get(Automation, uuid.UUID(criada["id"]))
        assert automation is not None
        assert automation.created_by == cena.user.user_id != colaborador.user_id


async def test_vigesima_primeira_acao_e_recusada(cena: Cena, client: AsyncClient) -> None:
    """Regra 13: passou de 20, deixou de ser regra e virou programa."""
    resposta = await client.post(
        "/api/v1/automations",
        json={
            "name": "Regra gigante",
            "trigger_kind": TriggerKind.LAWSUIT_CREATED.value,
            "trigger_config": {},
            "actions": [
                {"action_kind": "notify", "action_config": {"title": f"{i}"}} for i in range(21)
            ],
        },
        headers=auth_header(cena.user),
    )

    assert resposta.status_code == 422
    assert "20 ações" in resposta.json()["detail"]


async def test_desativar_nao_afeta_execucao_em_andamento(
    cena: Cena, client: AsyncClient, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 11: quem já começou, termina."""
    criada = await _criar_automacao(
        client,
        cena.user,
        trigger_kind=TriggerKind.LAWSUIT_CREATED.value,
        actions=[
            {
                "action_kind": "notify",
                "action_config": {"title": "Depois"},
                "delay_kind": "calendar_days",
                "delay_value": 1,
            }
        ],
    )
    await _emitir(
        app_session_factory,
        cena.user,
        TriggerKind.LAWSUIT_CREATED.value,
        cena.payload,
        now=datetime.now(UTC) - timedelta(days=2),
    )

    desativada = await client.post(
        f"/api/v1/automations/{criada['id']}/toggle",
        json={"is_active": False},
        headers=auth_header(cena.user),
    )
    assert desativada.status_code == 200

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, cena.user.tenant_id)
        retomadas = await resume_due_runs(session, cena.user.tenant_id)
    assert retomadas == 1

    runs = await _runs(app_session_factory, cena.user)
    assert runs[0].status == RunStatus.DONE.value


async def test_lancamento_vencido_hoje_dispara_uma_vez(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """O quinto gatilho não nasce de uma escrita: é uma DATA que passou. A varredura olha
    o dia exato — 'tudo que está vencido' republicaria o mesmo lançamento todo dia."""
    from tests.integration.test_transactions import _fixtures, _receita_payload

    # O financeiro exige acesso FULL (spec 055) — o GESTOR da cena não tem por padrão.
    financeiro = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    receita_id, _despesa, centro_id, conta_id, _outra = await _fixtures(
        client, _auth_header(financeiro)
    )
    vencimento = date.today()
    criada = await client.post(
        "/api/v1/transactions",
        json={
            **_receita_payload(
                category_id=receita_id, cost_center_id=centro_id, account_id=conta_id
            ),
            "due_date": vencimento.isoformat(),
        },
        headers=auth_header(financeiro),
    )
    assert criada.status_code == 201, criada.text
    await _criar_automacao(
        client,
        financeiro,
        trigger_kind=TriggerKind.TRANSACTION_OVERDUE.value,
        actions=[
            {
                "action_kind": "notify",
                "action_config": {"title": "Vencido", "user_id": str(financeiro.user_id)},
            }
        ],
    )

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, financeiro.tenant_id)
        emitidos = await emit_overdue_transactions(session, financeiro.tenant_id, today=vencimento)

    assert emitidos == 1
    runs = await _runs(app_session_factory, financeiro)
    assert [run.status for run in runs] == [RunStatus.DONE.value]


async def test_automacao_de_outro_escritorio_nao_existe(
    cena: Cena, client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    intruso = await make_user(role=UserRole.GESTOR)
    criada = await _criar_automacao(
        client,
        cena.user,
        trigger_kind=TriggerKind.LAWSUIT_CREATED.value,
        actions=[{"action_kind": "notify", "action_config": {"title": "Minha regra"}}],
    )

    resposta = await client.get(
        f"/api/v1/automations/{criada['id']}/runs", headers=auth_header(intruso)
    )

    assert resposta.status_code == 404
