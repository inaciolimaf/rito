"""Escrita feita por IA (spec 084).

A spec inteira existe para sustentar uma frase: **nada é gravado sem confirmação
humana**. Os testes atacam essa frase por todos os lados — chamando a ferramenta e
conferindo que o banco não mudou, aprovando com o usuário errado, tentando alterar o
log de auditoria, deixando a proposta expirar.
"""

import asyncio
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
from app.domain.ai.actions import (
    ActionForbiddenError,
    ActionNotPendingError,
    AiActionService,
    UndoNotAllowedError,
)
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


@pytest.mark.commits
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


# ------------------------------------------------ spec 133: uma confirmação, uma escrita


@pytest.mark.commits
async def test_duas_aprovacoes_simultaneas_executam_uma_vez_so(
    scene: Scene, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """O §7.4 do `CLAUDE.md` em uma frase: uma confirmação humana, uma execução, um registro.

    `_ensure_pending` lia `status == "pending"` do objeto que a request já tinha em mãos. Em
    READ COMMITTED — o nível padrão do Postgres e o desta aplicação — duas requisições
    simultâneas liam as duas "pending", as duas passavam a guarda e as duas chamavam
    `definition.execute`. O gatilho não é um atacante: é um duplo clique no botão de
    confirmar, ou o retry de um cliente impaciente.

    O teste roda `@pytest.mark.commits` de propósito: dentro da transação de teste da 105 as
    duas sessões seriam a MESMA conexão, e um `SELECT … FOR UPDATE` não teria contra quem
    competir — o teste passaria verde com o defeito de volta.
    """
    resultado = await _propose(
        app_session_factory,
        scene.user,
        scene.thread_id,
        "update_customer",
        {"customer_id": scene.customer_id, "city": "Osasco"},
    )
    action_id = uuid.UUID(resultado["pending_action"]["action_id"])

    # A barreira é o que torna o teste honesto: sem ela, `gather` deixa a primeira corrotina
    # correr até o commit antes de a segunda tocar no banco, e o teste passa verde mesmo sem
    # trava nenhuma (conferido — as duas execuções não chegavam a se cruzar). Com ela, as
    # duas leem a ação "pending" ANTES de qualquer uma decidir, que é exatamente o duplo
    # clique que o defeito exigia.
    largada = asyncio.Barrier(2)

    async def aprovar() -> str:
        async with app_session_factory() as session, session.begin():
            await set_tenant_context(session, scene.user.tenant_id)
            quem = await session.get(User, scene.user.user_id)
            assert quem is not None
            service = AiActionService(session=session, tenant_id=scene.user.tenant_id)
            acao = await service.actions.get_by_id(action_id)
            assert acao is not None
            await largada.wait()
            try:
                await service.approve(acao, user=quem, model="fabricante-x/modelo-y")
            except ActionNotPendingError:
                return "409"
            return "executou"

    veredictos = await asyncio.gather(aprovar(), aprovar())

    assert sorted(veredictos) == ["409", "executou"], veredictos
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, scene.user.tenant_id)
        trilha = list((await session.scalars(select(AiAuditLog))).all())
    assert len(trilha) == 1, "duas linhas de auditoria = a escrita aconteceu duas vezes"


async def test_aprovar_reconfere_a_permissao_que_propor_conferiu(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A permissão é a do momento do ATO, não a do momento do pedido.

    Entre propor e aprovar existe o `ACTION_TTL` de uma hora. O gestor que tira o acesso
    financeiro de alguém às 14h espera que a mudança valha às 14h01 — e não que uma
    proposta das 13h30 continue executando com o crachá que ela não tem mais. A regra 6 da
    084 dizia que a ação sem permissão nasce rejeitada; ela nascia, e quem perdia a
    permissão depois executava assim mesmo.
    """
    quem = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    thread_id = await _thread(app_session_factory, quem)
    resultado = await _propose(
        app_session_factory,
        quem,
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
    assert resultado["pending_action"]["status"] == "pending"
    action_id = uuid.UUID(resultado["pending_action"]["action_id"])

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, quem.tenant_id)
        await session.execute(
            update(User)
            .where(User.id == quem.user_id)
            .values(financial_access=FinancialAccess.NONE)
        )

    acao = await _decide(app_session_factory, quem, action_id, approve=True)

    assert acao.status == AiActionStatus.FAILED.value
    assert "acesso financeiro" in (acao.error or "")
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, quem.tenant_id)
        assert (
            list((await session.scalars(select(AiAuditLog))).all()) == []
        ), "nada foi executado; uma linha de auditoria aqui diria o contrário"


async def _undo(
    sessions: async_sessionmaker[AsyncSession], user: SeededUser, action_id: uuid.UUID
) -> None:
    async with sessions() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        who = await session.get(User, user.user_id)
        assert who is not None
        service = AiActionService(session=session, tenant_id=user.tenant_id)
        action = await service.actions.get_by_id(action_id)
        assert action is not None
        await service.undo(action, user=who)


async def test_desfazer_grava_no_log_de_auditoria(
    scene: Scene, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 7 da 084 e §7.4 do `CLAUDE.md`: **toda** escrita da IA passa pelo log.

    `undo` chamava `definition.execute` — uma escrita de domínio de verdade — e gravava
    apenas `undone_at` na própria ação. Quem auditasse o contato seis meses depois via o
    valor voltar ao antigo sem nenhuma linha explicando quem mandou voltar. A regra valia
    para a ida e não para a volta.

    O par antes/depois da linha nova é o inverso do da execução: sai do estado que a IA
    gravou e chega ao `before_state` original.
    """
    resultado = await _propose(
        app_session_factory,
        scene.user,
        scene.thread_id,
        "update_customer",
        {"customer_id": scene.customer_id, "city": "Sorocaba"},
    )
    action_id = uuid.UUID(resultado["pending_action"]["action_id"])
    await _decide(app_session_factory, scene.user, action_id, approve=True)
    await _undo(app_session_factory, scene.user, action_id)

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, scene.user.tenant_id)
        trilha = list(
            (await session.scalars(select(AiAuditLog).order_by(AiAuditLog.created_at))).all()
        )

    assert [linha.tool_name for linha in trilha] == ["update_customer", "update_customer:undo"]
    assert trilha[1].action_id == action_id
    assert trilha[1].user_id == scene.user.user_id
    assert (trilha[1].before_state or {}).get("city") == "Sorocaba"
    assert (trilha[1].after_state or {}).get("city") is None


async def test_desfazer_duas_vezes_e_recusado(
    scene: Scene, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """`undone_at` não era consultado por ninguém.

    Como o restore não gerava linha de auditoria, o guarda do "alguém mexeu depois"
    continuava passando e o mesmo desfazer podia ser repetido dentro dos 5 minutos. Cada
    repetição é uma escrita de domínio e — depois desta spec — uma linha de auditoria a
    mais dizendo que alguém desfez algo que já estava desfeito.
    """
    resultado = await _propose(
        app_session_factory,
        scene.user,
        scene.thread_id,
        "update_customer",
        {"customer_id": scene.customer_id, "city": "Jundiaí"},
    )
    action_id = uuid.UUID(resultado["pending_action"]["action_id"])
    await _decide(app_session_factory, scene.user, action_id, approve=True)
    await _undo(app_session_factory, scene.user, action_id)

    with pytest.raises(UndoNotAllowedError, match="já foi desfeita"):
        await _undo(app_session_factory, scene.user, action_id)
