"""Escrita feita por IA (spec 084).

A spec inteira existe para sustentar uma frase: **nada é gravado sem confirmação
humana**. Os testes atacam essa frase por todos os lados — chamando a ferramenta e
conferindo que o banco não mudou, aprovando com o usuário errado, tentando alterar o
log de auditoria, deixando a proposta expirar.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.tools.base import ToolContext
from app.ai.tools.runner import ToolRunner
from app.ai.tools.write import all_write_tools
from app.core.rls import set_tenant_context
from app.domain.ai.actions import ActionForbiddenError, AiActionService, UndoNotAllowedError
from app.domain.ai.models import AiAction, AiActionStatus, AiAuditLog, AiThread, ThreadStatus
from app.domain.customers.models import Customer
from app.domain.users.models import FinancialAccess, User, UserRole
from tests.integration.conftest import SeededUser, auth_header
from tests.integration.test_lawsuits import _auth_header, _create_customer


@dataclass
class Scene:
    user: SeededUser
    thread_id: uuid.UUID
    customer_id: str
    customer_name: str
    origin_id: str


async def _thread(sessions: async_sessionmaker[AsyncSession], user: SeededUser) -> uuid.UUID:
    async with sessions() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        thread = AiThread(
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            graph_name="base_agent",
            feature_key="copilot",
            status=ThreadStatus.RUNNING.value,
        )
        session.add(thread)
        await session.flush()
        return thread.id


@pytest.fixture
async def scene(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> Scene:
    user = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    headers = _auth_header(user)
    nome = f"Contato Original {uuid.uuid4().hex[:6]}"
    customer_id = await _create_customer(client, headers, nome)
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        cliente = await session.get(Customer, uuid.UUID(customer_id))
        assert cliente is not None
        origin_id = str(cliente.origin_id)
    return Scene(
        user=user,
        thread_id=await _thread(app_session_factory, user),
        customer_id=customer_id,
        customer_name=nome,
        origin_id=origin_id,
    )


async def _propose(
    sessions: async_sessionmaker[AsyncSession],
    user: SeededUser,
    thread_id: uuid.UUID | None,
    tool: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Chama a ferramenta como o agente chamaria — pelo runner."""
    async with sessions() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        actor = await session.get(User, user.user_id)
        assert actor is not None
        runner = ToolRunner(
            ToolContext(
                session=session,
                tenant_id=user.tenant_id,
                user=actor,
                thread_id=thread_id,
            )
        )
        return await runner.call(tool, arguments)


async def _actions(sessions: async_sessionmaker[AsyncSession], user: SeededUser) -> list[AiAction]:
    async with sessions() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        return list((await session.scalars(select(AiAction))).all())


async def _decide(
    sessions: async_sessionmaker[AsyncSession],
    user: SeededUser,
    action_id: uuid.UUID,
    *,
    approve: bool,
    reason: str | None = None,
    actor: SeededUser | None = None,
) -> AiAction:
    decisor = actor or user
    async with sessions() as session, session.begin():
        await set_tenant_context(session, decisor.tenant_id)
        who = await session.get(User, decisor.user_id)
        assert who is not None
        service = AiActionService(session=session, tenant_id=decisor.tenant_id)
        action = await service.actions.get_by_id(action_id)
        assert action is not None
        if approve:
            await service.approve(action, user=who, model="fabricante-x/modelo-y")
        else:
            await service.reject(action, user=who, reason=reason)
        return action


async def test_ferramenta_de_escrita_cria_acao_pendente_e_nao_grava(
    scene: Scene, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 1 — o teste mais importante da spec: chamar a ferramenta NÃO grava."""
    resultado = await _propose(
        app_session_factory,
        scene.user,
        scene.thread_id,
        "create_customer",
        {"name": "Cliente Proposto", "type": "PF", "origin_id": scene.origin_id},
    )

    assert resultado["pending_action"]["status"] == "pending"
    assert "Nada foi gravado" in resultado["note"]

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, scene.user.tenant_id)
        nomes = [row.name for row in (await session.scalars(select(Customer))).all()]
    assert "Cliente Proposto" not in nomes, "a ferramenta não pode ter gravado nada"

    acoes = await _actions(app_session_factory, scene.user)
    assert len(acoes) == 1
    assert acoes[0].status == AiActionStatus.PENDING.value
    preview = acoes[0].preview
    assert preview["changes"]["name"] == {"after": "Cliente Proposto"}


async def test_aprovar_executa_e_audita(
    scene: Scene, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regras 5 e 7: executa pelo service do domínio e registra antes/depois."""
    resultado = await _propose(
        app_session_factory,
        scene.user,
        scene.thread_id,
        "create_customer",
        {"name": "Cliente Aprovado", "type": "PF", "origin_id": scene.origin_id},
    )
    action_id = uuid.UUID(resultado["pending_action"]["action_id"])

    action = await _decide(app_session_factory, scene.user, action_id, approve=True)

    assert action.status == AiActionStatus.EXECUTED.value
    assert action.affected_id is not None

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, scene.user.tenant_id)
        nomes = [row.name for row in (await session.scalars(select(Customer))).all()]
        auditoria = list((await session.scalars(select(AiAuditLog))).all())

    assert "Cliente Aprovado" in nomes
    assert len(auditoria) == 1
    assert auditoria[0].tool_name == "create_customer"
    assert auditoria[0].model == "fabricante-x/modelo-y"
    depois = auditoria[0].after_state or {}
    assert depois["name"] == "Cliente Aprovado"
    assert auditoria[0].thread_id == scene.thread_id


async def test_rejeitar_nao_grava_nada(
    scene: Scene, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    resultado = await _propose(
        app_session_factory,
        scene.user,
        scene.thread_id,
        "create_customer",
        {"name": "Cliente Recusado", "type": "PF", "origin_id": scene.origin_id},
    )
    action_id = uuid.UUID(resultado["pending_action"]["action_id"])

    action = await _decide(
        app_session_factory,
        scene.user,
        action_id,
        approve=False,
        reason="já existe esse cliente",
    )

    assert action.status == AiActionStatus.REJECTED.value
    assert action.rejection_reason == "já existe esse cliente"
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, scene.user.tenant_id)
        nomes = [row.name for row in (await session.scalars(select(Customer))).all()]
        auditoria = list((await session.scalars(select(AiAuditLog))).all())
    assert "Cliente Recusado" not in nomes
    assert auditoria == []


async def test_nem_colega_nem_gestor_aprovam_pelo_dono(
    scene: Scene,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
) -> None:
    """Regra 3: aprovar é assinar embaixo — perfil de gestão não transfere isso."""
    colega = await make_user(tenant_id=scene.user.tenant_id, role=UserRole.COLABORADOR)
    gestor = await make_user(tenant_id=scene.user.tenant_id, role=UserRole.GESTOR)
    resultado = await _propose(
        app_session_factory,
        scene.user,
        scene.thread_id,
        "create_customer",
        {"name": "Cliente de Outro", "type": "PF", "origin_id": scene.origin_id},
    )
    action_id = resultado["pending_action"]["action_id"]

    for quem in (colega, gestor):
        resposta = await client.post(
            f"/api/v1/ai/actions/{action_id}/approve", headers=auth_header(quem)
        )
        assert resposta.status_code == 403, f"{quem.role} não pode aprovar pelo dono"

    with pytest.raises(ActionForbiddenError):
        await _decide(
            app_session_factory, scene.user, uuid.UUID(action_id), approve=True, actor=gestor
        )


async def test_acao_expira_em_uma_hora(
    scene: Scene, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 4 — sem `sleep`: o relógio é injetado."""
    await _propose(
        app_session_factory,
        scene.user,
        scene.thread_id,
        "create_customer",
        {"name": "Cliente Esquecido", "type": "PF", "origin_id": scene.origin_id},
    )

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, scene.user.tenant_id)
        service = AiActionService(session=session, tenant_id=scene.user.tenant_id)
        expiradas = await service.expire_pending(now=datetime.now(UTC) + timedelta(hours=2))

    assert expiradas == 1
    acoes = await _actions(app_session_factory, scene.user)
    assert acoes[0].status == AiActionStatus.EXPIRED.value


async def test_execucao_respeita_as_regras_do_service(
    scene: Scene, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 5: a IA não é caminho paralelo. Categoria inexistente reprova na IA
    exatamente como reprovaria num formulário."""
    resultado = await _propose(
        app_session_factory,
        scene.user,
        scene.thread_id,
        "create_transaction",
        {
            "kind": "RECEITA",
            "amount": "100.00",
            "due_date": "2026-09-10",
            "category_id": str(uuid.uuid4()),
            "cost_center_id": str(uuid.uuid4()),
            "debit_account_id": str(uuid.uuid4()),
        },
    )
    action_id = uuid.UUID(resultado["pending_action"]["action_id"])

    action = await _decide(app_session_factory, scene.user, action_id, approve=True)

    assert action.status == AiActionStatus.FAILED.value
    assert action.error is not None
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, scene.user.tenant_id)
        assert list((await session.scalars(select(AiAuditLog))).all()) == []


async def test_sem_permissao_a_acao_nasce_rejeitada(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 6: a tentativa fica registrada — é informação para quem lê a conversa."""
    sem_financeiro = await make_user(
        role=UserRole.COLABORADOR, financial_access=FinancialAccess.NONE
    )
    thread_id = await _thread(app_session_factory, sem_financeiro)

    resultado = await _propose(
        app_session_factory,
        sem_financeiro,
        thread_id,
        "create_transaction",
        {
            "kind": "RECEITA",
            "amount": "10.00",
            "due_date": "2026-09-10",
            "category_id": str(uuid.uuid4()),
            "cost_center_id": str(uuid.uuid4()),
            "debit_account_id": str(uuid.uuid4()),
        },
    )

    assert resultado["pending_action"]["status"] == "rejected"
    acoes = await _actions(app_session_factory, sem_financeiro)
    assert acoes[0].status == AiActionStatus.REJECTED.value
    assert "acesso financeiro" in (acoes[0].rejection_reason or "")


async def test_preview_mostra_o_diff_da_atualizacao(
    scene: Scene, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 2: em atualização, o preview é o antes/depois — e só do que muda."""
    resultado = await _propose(
        app_session_factory,
        scene.user,
        scene.thread_id,
        "update_customer",
        {"customer_id": scene.customer_id, "city": "Campinas", "notes": "Cliente VIP"},
    )

    preview = resultado["pending_action"]["preview"]
    assert preview["affected_type"] == "customer"
    assert preview["changes"]["city"] == {"before": None, "after": "Campinas"}
    assert preview["changes"]["notes"] == {"before": None, "after": "Cliente VIP"}
    # O nome não foi pedido, então não aparece: preview com campo intocado esconde a
    # mudança real no meio do ruído.
    assert "name" not in preview["changes"]


async def test_ai_audit_log_recusa_update_e_delete(
    scene: Scene,
    app_session_factory: async_sessionmaker[AsyncSession],
    admin_engine: Any,
) -> None:
    """Regra 8: append-only garantido pelo BANCO — inclusive contra o superusuário."""
    resultado = await _propose(
        app_session_factory,
        scene.user,
        scene.thread_id,
        "create_customer",
        {"name": "Cliente Auditado", "type": "PF", "origin_id": scene.origin_id},
    )
    await _decide(
        app_session_factory,
        scene.user,
        uuid.UUID(resultado["pending_action"]["action_id"]),
        approve=True,
    )

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, scene.user.tenant_id)
        entrada = (await session.scalars(select(AiAuditLog))).one()
        entry_id = entrada.id

    # Pela role da aplicação: sem privilégio (REVOKE) e barrada pela trigger.
    async with app_session_factory() as session:
        with pytest.raises(DBAPIError):
            async with session.begin():
                await set_tenant_context(session, scene.user.tenant_id)
                await session.execute(
                    update(AiAuditLog)
                    .where(AiAuditLog.id == entry_id)
                    .values(model="modelo-forjado")
                )

    # Pelo superusuário da migration: a trigger continua valendo.
    async with admin_engine.begin() as conn:
        with pytest.raises(DBAPIError):
            await conn.execute(text("DELETE FROM ai_audit_log WHERE id = :id"), {"id": entry_id})

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, scene.user.tenant_id)
        sobreviveu = (await session.scalars(select(AiAuditLog))).one()
    assert sobreviveu.model == "fabricante-x/modelo-y"


async def test_desfazer_dentro_de_cinco_minutos_restaura_o_estado(
    scene: Scene, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 10: desfazer é do humano e restaura o estado anterior."""
    resultado = await _propose(
        app_session_factory,
        scene.user,
        scene.thread_id,
        "update_customer",
        {"customer_id": scene.customer_id, "city": "Campinas"},
    )
    action_id = uuid.UUID(resultado["pending_action"]["action_id"])
    await _decide(app_session_factory, scene.user, action_id, approve=True)

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, scene.user.tenant_id)
        cliente = await session.get(Customer, uuid.UUID(scene.customer_id))
        assert cliente is not None and cliente.city == "Campinas"

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, scene.user.tenant_id)
        who = await session.get(User, scene.user.user_id)
        assert who is not None
        service = AiActionService(session=session, tenant_id=scene.user.tenant_id)
        action = await service.actions.get_by_id(action_id)
        assert action is not None
        await service.undo(action, user=who)

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, scene.user.tenant_id)
        cliente = await session.get(Customer, uuid.UUID(scene.customer_id))
        assert cliente is not None
        assert cliente.city is None, "o desfazer tinha que devolver o estado anterior"


async def test_desfazer_fora_da_janela_e_recusado(
    scene: Scene, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 10: passados os 5 minutos, desfazer sairia errado — melhor recusar."""
    resultado = await _propose(
        app_session_factory,
        scene.user,
        scene.thread_id,
        "update_customer",
        {"customer_id": scene.customer_id, "city": "Santos"},
    )
    action_id = uuid.UUID(resultado["pending_action"]["action_id"])
    await _decide(app_session_factory, scene.user, action_id, approve=True)

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, scene.user.tenant_id)
        who = await session.get(User, scene.user.user_id)
        assert who is not None
        service = AiActionService(session=session, tenant_id=scene.user.tenant_id)
        action = await service.actions.get_by_id(action_id)
        assert action is not None
        with pytest.raises(UndoNotAllowedError):
            await service.undo(action, user=who, now=datetime.now(UTC) + timedelta(minutes=6))


async def test_sexta_acao_pendente_no_thread_e_barrada(
    scene: Scene, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 12: enxurrada de aprovações é o mesmo que nenhuma — ninguém lê seis."""
    for indice in range(5):
        resultado = await _propose(
            app_session_factory,
            scene.user,
            scene.thread_id,
            "create_customer",
            {"name": f"Proposta {indice}", "type": "PF", "origin_id": scene.origin_id},
        )
        assert resultado["pending_action"]["status"] == "pending"

    sexta = await _propose(
        app_session_factory,
        scene.user,
        scene.thread_id,
        "create_customer",
        {"name": "Proposta 6", "type": "PF", "origin_id": scene.origin_id},
    )

    assert sexta["error"]["code"] == "too_many_pending"


def test_nenhuma_ferramenta_de_exclusao_no_registry() -> None:
    """Regra 13: a IA não apaga. Nem soft delete, nem arquivar — nunca."""
    proibidos = ("delete", "remove", "destroy", "archive", "excluir", "apagar", "arquivar")
    ofensores = [
        definition.name
        for definition in all_write_tools()
        if any(termo in definition.name.lower() for termo in proibidos)
    ]
    assert ofensores == [], f"ferramenta de exclusão no registry: {ofensores}"
    assert len(all_write_tools()) == 10
