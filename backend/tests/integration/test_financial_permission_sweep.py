"""Refatoração 060, Alvo 3 — varredura de permissão financeira: `financial_access=NONE`
não acessa nenhuma rota do módulo financeiro nem vê valor em endpoint de outro módulo
(painel do processo, cards do CRM). Complementa `test_permission_coverage.py` (que só
confirma que toda rota declara ALGUMA permissão) com o nível exigido de verdade."""

import uuid
from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.users.models import FinancialAccess, User, UserRole
from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuits import (
    _auth_header,
    _create_customer,
    _create_lawsuit,
    _create_lawsuit_type,
    _create_stage,
)

_FINANCIAL_GET_ROUTES = [
    "/api/v1/dre-groups",
    "/api/v1/financial-categories",
    "/api/v1/cost-centers",
    "/api/v1/bank-accounts",
    "/api/v1/bank-accounts/balances",
    "/api/v1/transactions",
    "/api/v1/transactions/stats",
    "/api/v1/transactions/chart",
]


@pytest.mark.parametrize("path", _FINANCIAL_GET_ROUTES)
async def test_financial_access_none_e_403_em_toda_rota_de_leitura(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]], path: str
) -> None:
    seeded = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.NONE)
    response = await client.get(path, headers=_auth_header(seeded))
    assert response.status_code == 403, path


async def test_financial_access_none_e_403_no_cash_flow(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    # Rota separada por exigir from/to (senão 422 mascararia o 403 checado acima).
    seeded = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.NONE)
    response = await client.get(
        "/api/v1/transactions/cash-flow",
        params={"from": "2026-08-01", "to": "2026-08-31"},
        headers=_auth_header(seeded),
    )
    assert response.status_code == 403


async def test_financial_access_none_e_403_no_painel_financeiro_do_processo(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor_full = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    headers_full = _auth_header(gestor_full)
    type_id, _group_id = await _create_lawsuit_type(client, headers_full)
    stage_id = await _create_stage(client, headers_full)
    customer_id = await _create_customer(client, headers_full, "Cliente Sweep")
    lawsuit = await _create_lawsuit(
        client,
        headers_full,
        user_id=str(gestor_full.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
        parties=[{"customer_id": customer_id, "pole": "ATIVO", "is_client": True}],
    )

    seeded_none = await make_user(
        tenant_id=gestor_full.tenant_id, role=UserRole.GESTOR, financial_access=FinancialAccess.NONE
    )
    response = await client.get(
        f"/api/v1/lawsuits/{lawsuit['id']}/financial-summary", headers=_auth_header(seeded_none)
    )
    assert response.status_code == 403


async def test_financial_access_none_nao_ve_valor_no_board_nem_nas_stats_do_crm(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor_full = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    headers_full = _auth_header(gestor_full)
    type_id, _group_id = await _create_lawsuit_type(client, headers_full)
    stage_id = await _create_stage(client, headers_full)
    created = await _create_lawsuit(
        client,
        headers_full,
        user_id=str(gestor_full.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
        case_value=5000.00,
    )
    assert created["case_value"] == 5000.00

    seeded_none = await make_user(
        tenant_id=gestor_full.tenant_id, role=UserRole.GESTOR, financial_access=FinancialAccess.NONE
    )
    headers_none = _auth_header(seeded_none)

    board = await client.get("/api/v1/crm/board", headers=headers_none)
    assert board.status_code == 200
    cards = [card for column in board.json()["columns"] for card in column["items"]]
    card = next(card for card in cards if card["id"] == created["id"])
    assert card["case_value"] is None

    stats = await client.get("/api/v1/crm/stats", headers=headers_none)
    assert stats.status_code == 200
    assert stats.json()["total_value"] is None

    # Com acesso, o mesmo board mostra o valor de verdade — a regra é o gate, não um
    # bug que zera pra todo mundo.
    board_full = await client.get("/api/v1/crm/board", headers=headers_full)
    cards_full = [card for column in board_full.json()["columns"] for card in column["items"]]
    card_full = next(card for card in cards_full if card["id"] == created["id"])
    assert card_full["case_value"] == 5000.00


# ------------------------------------------------- spec 134: a superfície pública


async def _emitir_token(
    client: AsyncClient, seeded: SeededUser, escopos: list[str]
) -> tuple[int, str]:
    resposta = await client.post(
        "/api/v1/api-tokens",
        json={
            "name": f"Integração {uuid.uuid4().hex[:6]}",
            "scopes": escopos,
            "allowed_ips": [],
            "expires_at": None,
        },
        headers=_auth_header(seeded),
    )
    return resposta.status_code, str(resposta.json().get("token", ""))


@pytest.mark.parametrize(
    ("acesso", "escopo", "esperado"),
    [
        (FinancialAccess.NONE, "read:transactions", 403),
        (FinancialAccess.NONE, "write:transactions", 403),
        (FinancialAccess.READ_ONLY, "read:transactions", 201),
        (FinancialAccess.READ_ONLY, "write:transactions", 403),
        (FinancialAccess.FULL, "write:transactions", 201),
        (FinancialAccess.NONE, "read:customers", 201),
    ],
)
async def test_emissao_de_token_confere_o_acesso_financeiro_de_quem_emite(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    acesso: FinancialAccess,
    escopo: str,
    esperado: int,
) -> None:
    """Spec 134, regra 2: o token delega o que o dono tem — nunca cria autoridade nova.

    Sem isto, um GESTOR com `financial_access=NONE` (403 em toda rota financeira da tela)
    emitia um `write:transactions` e passava a escrever o financeiro inteiro pela API
    pública. Escalada de privilégio intra-tenant de um passo só.
    """
    gestor = await make_user(role=UserRole.GESTOR, financial_access=acesso)

    status, _token = await _emitir_token(client, gestor, [escopo])

    assert status == esperado


async def test_token_financeiro_para_de_valer_quando_o_dono_perde_o_acesso(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Spec 134, regra 3: a permissão vale no momento do ATO, não no da emissão.

    O token emitido enquanto o dono tinha FULL sobrevive à mudança — e sobreviveria para
    sempre, porque token não expira sozinho. Conferir na chamada é o que faz "tirei o
    acesso financeiro dele às 14h" valer às 14h01, como vale na tela.
    """
    gestor = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    status, token = await _emitir_token(
        client, gestor, ["read:settings", "read:transactions", "write:transactions"]
    )
    assert status == 201
    cabecalho = {"Authorization": f"Bearer {token}"}
    assert (await client.get("/api/public/v1/transactions", headers=cabecalho)).status_code == 200

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, gestor.tenant_id)
        usuario = await session.get(User, gestor.user_id)
        assert usuario is not None
        usuario.financial_access = FinancialAccess.NONE

    leitura = await client.get("/api/public/v1/transactions", headers=cabecalho)
    escrita = await client.put(
        f"/api/public/v1/transactions/{uuid.uuid4()}",
        json={"description": "não deveria chegar aqui"},
        headers=cabecalho,
    )
    settings = await client.get("/api/public/v1/settings", headers=cabecalho)

    assert leitura.status_code == 403
    assert "acesso financeiro" in leitura.json()["detail"]
    assert escrita.status_code == 403, "403 antes do 404: o gate vem antes da busca"
    # `/settings` não é 403 — o resto dele serve a quem integra só cadastro —, mas as
    # referências financeiras somem, como somem em `/api/v1/bank-accounts`.
    assert settings.status_code == 200
    assert settings.json()["bank_accounts"] == []
    assert settings.json()["cost_centers"] == []
    assert settings.json()["financial_categories"] == []
    assert settings.json()["users"] != []


async def test_financial_access_none_nao_ve_valor_no_detalhe_do_processo(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Spec 135, regra 2 — o furo mais largo do eixo financeiro até esta spec.

    O card do CRM escondia `case_value` desde a 060, e a tela de detalhe do MESMO processo
    devolvia os quatro campos monetários para qualquer Colaborador. Só o `/financial-summary`
    tinha gate. A rota continua respondendo 200: o processo não é dado financeiro, o valor
    dele é.
    """
    gestor_full = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    headers_full = _auth_header(gestor_full)
    type_id, _group_id = await _create_lawsuit_type(client, headers_full)
    stage_id = await _create_stage(client, headers_full)
    created = await _create_lawsuit(
        client,
        headers_full,
        user_id=str(gestor_full.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
        case_value=5000.00,
        fees_value=750.00,
        fees_percentage=15.00,
        contingency="PROVAVEL",
    )

    seeded_none = await make_user(
        tenant_id=gestor_full.tenant_id,
        role=UserRole.COLABORADOR,
        financial_access=FinancialAccess.NONE,
    )
    detalhe = await client.get(
        f"/api/v1/lawsuits/{created['id']}", headers=_auth_header(seeded_none)
    )

    assert detalhe.status_code == 200
    corpo = detalhe.json()
    assert corpo["case_value"] is None
    assert corpo["fees_value"] is None
    assert corpo["fees_percentage"] is None
    assert corpo["contingency"] is None
    # O resto do processo continua de pé — é máscara de campo, não recusa de rota.
    assert corpo["id"] == created["id"]
    assert corpo["stage_id"] == stage_id


async def test_com_acesso_financeiro_o_detalhe_do_processo_mostra_os_valores(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """O par do teste acima: a regra é o gate, não um bug que zera para todo mundo."""
    gestor_full = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    headers_full = _auth_header(gestor_full)
    type_id, _group_id = await _create_lawsuit_type(client, headers_full)
    stage_id = await _create_stage(client, headers_full)
    created = await _create_lawsuit(
        client,
        headers_full,
        user_id=str(gestor_full.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
        case_value=5000.00,
        contingency="PROVAVEL",
    )

    leitor = await make_user(
        tenant_id=gestor_full.tenant_id,
        role=UserRole.COLABORADOR,
        financial_access=FinancialAccess.READ_ONLY,
    )
    detalhe = await client.get(f"/api/v1/lawsuits/{created['id']}", headers=_auth_header(leitor))

    assert detalhe.status_code == 200
    assert detalhe.json()["case_value"] == 5000.00
    assert detalhe.json()["contingency"] == "PROVAVEL"


async def test_a_mascara_vale_tambem_na_resposta_de_criar_e_de_atualizar(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """`POST` e `PUT` devolvem o processo pelo mesmo mapeador que o `GET`. Mascarar só a
    leitura deixaria o valor sair pela resposta da escrita — o mesmo dado, outra porta."""
    gestor_none = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.NONE)
    headers = _auth_header(gestor_none)
    type_id, _group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)

    created = await _create_lawsuit(
        client,
        headers,
        user_id=str(gestor_none.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
        case_value=1234.00,
    )
    assert created["case_value"] is None

    atualizado = await client.put(
        f"/api/v1/lawsuits/{created['id']}",
        json={
            "user_id": str(gestor_none.user_id),
            "lawsuit_type_id": type_id,
            "stage_id": stage_id,
            "folder": "Pasta 1",
        },
        headers=headers,
    )
    assert atualizado.status_code == 200, atualizado.text
    assert atualizado.json()["case_value"] is None
