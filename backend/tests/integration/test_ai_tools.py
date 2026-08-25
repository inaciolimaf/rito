"""Ferramentas de leitura (spec 083).

O teste que carrega a spec é o parametrizado: **cada uma das 16 ferramentas, chamada
por um usuário de OUTRO tenant apontando para o dado do primeiro, não devolve nada.**
Uma ferramenta que ignore o RLS é vazamento com cara de feature — e o agente é o
usuário mais persistente que o sistema já teve.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.tools.base import ToolContext, all_tools, tool_specs
from app.ai.tools.runner import ToolRunner, cap_output
from app.core.rls import set_tenant_context
from app.domain.ai.models import AiToolCall
from app.domain.lawsuits.cnj import CNJNumber, compute_check_digit, format_cnj
from app.domain.users.models import FinancialAccess, User, UserRole
from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuits import (
    _auth_header,
    _create_customer,
    _create_lawsuit,
    _create_lawsuit_type,
    _create_stage,
)
from tests.integration.test_posts import _create_post, _create_task_type
from tests.integration.test_publications_listing import make_publication
from tests.integration.test_transactions import _fixtures, _receita_payload


@dataclass
class Fixture:
    """Um escritório com um pouco de cada coisa — o alvo do teste de vazamento."""

    user: SeededUser
    customer_id: str
    customer_name: str
    lawsuit_id: str
    process_number: str
    folder: str
    post_id: str
    publication_id: uuid.UUID
    task_type_name: str


async def _seed_office(
    client: Any,
    make_user: Callable[..., Awaitable[SeededUser]],
    sessions: async_sessionmaker[AsyncSession],
) -> Fixture:
    gestor = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    headers = _auth_header(gestor)
    suffix = uuid.uuid4().hex[:8]
    customer_name = f"Cliente Sigiloso {suffix}"
    customer_id = await _create_customer(client, headers, customer_name)
    type_id, _group = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    # O número do processo passa pela validação de dígito verificador (spec 025), então
    # é computado, não inventado — o marcador de vazamento é a pasta, que é livre.
    sequential = f"{abs(hash(suffix)) % 10_000_000:07d}"
    process_number = format_cnj(
        CNJNumber(
            sequential=sequential,
            check_digit=compute_check_digit(f"{sequential}20268260100"),
            year=2026,
            segment=8,
            court="26",
            origin="0100",
        )
    )
    folder = f"PASTA-{suffix}"
    lawsuit = await _create_lawsuit(
        client,
        headers,
        user_id=str(gestor.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
        process_number=process_number,
        folder=folder,
        case_value=12345,
        parties=[{"customer_id": customer_id, "pole": "ATIVO", "is_client": True}],
    )
    task_type_id = await _create_task_type(client, headers)
    post = await _create_post(
        client,
        headers,
        lawsuit_id=str(lawsuit["id"]),
        task_type_id=task_type_id,
        user_ids=[str(gestor.user_id)],
        scheduled_date=date.today().isoformat(),
    )
    publication_id = await make_publication(
        sessions, gestor.tenant_id, process_number=process_number
    )
    receita_id, _despesa, cost_center_id, account_id, _b = await _fixtures(client, headers)
    criado = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id, cost_center_id=cost_center_id, account_id=account_id
        ),
        headers=headers,
    )
    assert criado.status_code == 201, criado.text
    return Fixture(
        user=gestor,
        customer_id=customer_id,
        customer_name=customer_name,
        lawsuit_id=str(lawsuit["id"]),
        process_number=process_number,
        folder=folder,
        post_id=str(post["id"]),
        publication_id=publication_id,
        task_type_name=str(post["task_type_name"]),
    )


async def _context(
    sessions: async_sessionmaker[AsyncSession], seeded: SeededUser, session: AsyncSession
) -> ToolContext:
    user = await session.get(User, seeded.user_id)
    assert user is not None
    return ToolContext(session=session, tenant_id=seeded.tenant_id, user=user)


async def _call(
    sessions: async_sessionmaker[AsyncSession],
    seeded: SeededUser,
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    async with sessions() as session, session.begin():
        await set_tenant_context(session, seeded.tenant_id)
        ctx = await _context(sessions, seeded, session)
        runner = ToolRunner(ctx)
        return await runner.call(name, arguments)


def _leak_arguments(fixture: Fixture) -> dict[str, dict[str, Any]]:
    """Para cada ferramenta, o argumento que MAIS tentaria vazar o dado do outro
    escritório: o id exato, ou a busca pelo nome/número exato."""
    hoje = date.today()
    return {
        "search_customers": {"query": fixture.customer_name},
        "get_customer": {"customer_id": fixture.customer_id},
        "search_lawsuits": {"query": fixture.folder},
        "get_lawsuit": {"lawsuit_id": fixture.lawsuit_id},
        "get_lawsuit_timeline": {"lawsuit_id": fixture.lawsuit_id},
        "search_tasks": {
            "date_from": (hoje - timedelta(days=1)).isoformat(),
            "date_to": (hoje + timedelta(days=1)).isoformat(),
        },
        "get_inbox": {"section": "unread"},
        "search_publications": {
            "date_from": (hoje - timedelta(days=7)).isoformat(),
            "date_to": hoje.isoformat(),
            "process_number": fixture.process_number,
        },
        "get_publication": {"publication_id": str(fixture.publication_id)},
        "search_transactions": {},
        "get_financial_summary": {},
        "get_lawsuit_financials": {"lawsuit_id": fixture.lawsuit_id},
        "get_productivity": {},
        "get_bi_metrics": {"metric": "pipeline"},
        "list_taxonomies": {"kind": "all"},
        "get_current_context": {},
    }


def _leaks(payload: dict[str, Any], fixture: Fixture) -> bool:
    """Vazou se qualquer identificador do outro escritório aparecer na resposta."""
    blob = str(payload)
    marcadores = (
        fixture.folder,
        fixture.customer_name,
        fixture.customer_id,
        fixture.lawsuit_id,
        fixture.process_number,
        fixture.post_id,
        str(fixture.publication_id),
        fixture.task_type_name,
    )
    return any(marcador in blob for marcador in marcadores)


@pytest.fixture
async def office(
    client: Any,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> Fixture:
    return await _seed_office(client, make_user, app_session_factory)


async def test_as_dezesseis_ferramentas_respeitam_o_tenant(
    office: Fixture,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """O teste mais importante da spec. O intruso é GESTOR com acesso financeiro FULL
    no PRÓPRIO escritório — o que o barra não é RBAC, é o RLS."""
    intruso = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    argumentos = _leak_arguments(office)
    nomes = {definition.name for definition in all_tools()}
    assert set(argumentos) == nomes, "toda ferramenta precisa de um caso de vazamento"

    vazamentos: list[str] = []
    for nome, args in argumentos.items():
        payload = await _call(app_session_factory, intruso, nome, args)
        if _leaks(payload, office):
            vazamentos.append(f"{nome}: {payload}")

    assert vazamentos == [], f"ferramenta vazando dado de outro tenant: {vazamentos}"


async def test_ferramenta_financeira_com_acesso_none_devolve_erro_tipado(
    office: Fixture,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 2: o agente não tem privilégio próprio — e o erro é uma mensagem que ele
    consegue explicar, não uma exceção."""
    sem_financeiro = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.NONE)

    payload = await _call(app_session_factory, sem_financeiro, "search_transactions", {})

    assert payload["error"]["code"] == "forbidden_financial"

    # E a ferramenta nem é oferecida ao modelo: token gasto em tentativa proibida é
    # token jogado fora.
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, sem_financeiro.tenant_id)
        user = await session.get(User, sem_financeiro.user_id)
        assert user is not None
        oferecidas = {spec.name for spec in tool_specs(user)}
    assert "search_transactions" not in oferecidas
    assert "search_lawsuits" in oferecidas


async def test_tarefa_privada_de_terceiro_nao_aparece(
    client: Any,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 3: privada é privada também para o agente do colega."""
    dono = await make_user(role=UserRole.GESTOR)
    colega = await make_user(tenant_id=dono.tenant_id, role=UserRole.GESTOR)
    headers = _auth_header(dono)
    type_id, _group = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    lawsuit = await _create_lawsuit(
        client, headers, user_id=str(dono.user_id), lawsuit_type_id=type_id, stage_id=stage_id
    )
    task_type_id = await _create_task_type(client, headers)
    privada = await _create_post(
        client,
        headers,
        lawsuit_id=str(lawsuit["id"]),
        task_type_id=task_type_id,
        user_ids=[str(dono.user_id)],
        scheduled_date=date.today().isoformat(),
        is_private=True,
    )

    do_dono = await _call(
        app_session_factory,
        dono,
        "search_tasks",
        {"date_from": date.today().isoformat(), "date_to": date.today().isoformat()},
    )
    do_colega = await _call(
        app_session_factory,
        colega,
        "search_tasks",
        {"date_from": date.today().isoformat(), "date_to": date.today().isoformat()},
    )

    assert str(privada["id"]) in str(do_dono)
    assert str(privada["id"]) not in str(do_colega)


async def test_limite_de_linhas_marca_truncado(
    client: Any,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 4: o agente precisa SABER que a lista está incompleta — senão conclui por
    uma amostra e apresenta como se fosse o todo."""
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    for indice in range(4):
        await _create_customer(client, headers, f"Contato Repetido {indice}")

    payload = await _call(app_session_factory, gestor, "search_customers", {"limit": 2})

    assert len(payload["items"]) == 2
    assert payload["truncated"] is True


def test_saida_acima_de_20kb_e_resumida() -> None:
    """Regra 5: corta por LINHAS e avisa — meio JSON quebrado seria pior para o modelo
    do que menos linhas."""
    grande = {"items": [{"texto": "x" * 2000} for _ in range(50)], "total": 50}

    resultado = cap_output(grande)

    assert resultado["truncated"] is True
    assert len(resultado["items"]) < 50
    assert "Refine os filtros" in resultado["truncation_note"]


async def test_chamada_e_registrada_em_ai_tool_calls(
    office: Fixture, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 6: o que a IA olhou fica registrado — é auditoria de acesso a dado."""
    await _call(
        app_session_factory,
        office.user,
        "search_customers",
        {"query": office.customer_name},
    )

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, office.user.tenant_id)
        rows = list((await session.scalars(select(AiToolCall))).all())

    assert len(rows) == 1
    assert rows[0].tool_name == "search_customers"
    assert rows[0].arguments == {"query": office.customer_name}
    assert rows[0].row_count == 1
    assert rows[0].duration_ms is not None
    assert rows[0].error is None


async def test_erro_vira_mensagem_estruturada_e_fica_registrado(
    office: Fixture, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 8: nem argumento inválido, nem id inexistente, nem ferramenta desconhecida
    derrubam o grafo."""
    inexistente = await _call(
        app_session_factory, office.user, "get_customer", {"customer_id": str(uuid.uuid4())}
    )
    argumento_ruim = await _call(
        app_session_factory, office.user, "search_customers", {"limit": 999}
    )
    desconhecida = await _call(app_session_factory, office.user, "nao_existe", {})

    assert inexistente["error"]["code"] == "not_found"
    assert argumento_ruim["error"]["code"] == "invalid_arguments"
    assert desconhecida["error"]["code"] == "unknown_tool"

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, office.user.tenant_id)
        rows = list((await session.scalars(select(AiToolCall))).all())
    assert len(rows) == 3
    assert all(row.error is not None for row in rows)


async def test_decima_primeira_chamada_no_mesmo_passo_e_barrada(
    office: Fixture, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Regra 11: um passo que consulta o banco sem parar é laço com outro nome."""
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, office.user.tenant_id)
        ctx = await _context(app_session_factory, office.user, session)
        runner = ToolRunner(ctx)
        resultados = [await runner.call("list_taxonomies", {"kind": "steps"}) for _ in range(11)]

    assert all("error" not in resultado for resultado in resultados[:10])
    assert resultados[10]["error"]["code"] == "too_many_calls"

    # Passo novo, orçamento novo.
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, office.user.tenant_id)
        ctx = await _context(app_session_factory, office.user, session)
        runner = ToolRunner(ctx)
        runner.calls_in_step = 10
        runner.begin_step()
        depois = await runner.call("list_taxonomies", {"kind": "steps"})
    assert "error" not in depois
