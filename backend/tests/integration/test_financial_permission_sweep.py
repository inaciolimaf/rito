"""Refatoração 060, Alvo 3 — varredura de permissão financeira: `financial_access=NONE`
não acessa nenhuma rota do módulo financeiro nem vê valor em endpoint de outro módulo
(painel do processo, cards do CRM). Complementa `test_permission_coverage.py` (que só
confirma que toda rota declara ALGUMA permissão) com o nível exigido de verdade."""

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient

from app.domain.users.models import FinancialAccess, UserRole
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
