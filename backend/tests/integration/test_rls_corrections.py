"""Spec 101, §10: isolamento por tenant nos cinco fluxos de transferência/exclusão que
deixaram de ser stub (CLAUDE.md §4 — "tenant A não enxerga dado de tenant B").

O risco que estes testes fecham é específico das guardas novas: `usage_count` e
`reassign` são queries CRUAS, sem `WHERE tenant_id` (quem filtra é o RLS). Se alguma
delas rodasse fora do contexto de tenant, o `transfer` do tenant A reatribuiria linhas
do tenant B, e a guarda de exclusão de A veria uso de B. Cada teste abaixo cria a
referência em B e prova que A não a enxerga.
"""

import uuid
from collections.abc import Awaitable, Callable
from decimal import Decimal

from httpx import AsyncClient

from app.core.tokens import create_access_token
from app.domain.users.models import FinancialAccess, UserRole
from tests.integration.conftest import SeededUser


def _auth_header(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)
    return {"Authorization": f"Bearer {token}"}


async def _two_tenants(
    make_user: Callable[..., Awaitable[SeededUser]],
) -> tuple[tuple[SeededUser, dict[str, str]], tuple[SeededUser, dict[str, str]]]:
    a = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    b = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    assert a.tenant_id != b.tenant_id
    return (a, _auth_header(a)), (b, _auth_header(b))


async def _create_stage(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        "/api/v1/stages",
        json={"name": f"Etapa {uuid.uuid4().hex[:8]}", "step_id": 1},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    result: str = response.json()["id"]
    return result


async def _create_origin(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        "/api/v1/customer-origins",
        json={"name": f"Origem {uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    result: str = response.json()["id"]
    return result


async def _create_customer(client: AsyncClient, headers: dict[str, str], origin_id: str) -> str:
    response = await client.post(
        "/api/v1/customers",
        json={"type": "PF", "name": f"Cliente {uuid.uuid4().hex[:8]}", "origin_id": origin_id},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    result: str = response.json()["id"]
    return result


async def _create_lawsuit(
    client: AsyncClient, headers: dict[str, str], seeded: SeededUser, stage_id: str
) -> str:
    suffix = uuid.uuid4().hex[:8]
    group = await client.post(
        "/api/v1/action-groups", json={"name": f"Grupo {suffix}"}, headers=headers
    )
    assert group.status_code == 201
    lawsuit_type = await client.post(
        "/api/v1/lawsuit-types",
        json={"name": f"Tipo {suffix}", "action_group_id": group.json()["id"]},
        headers=headers,
    )
    assert lawsuit_type.status_code == 201
    customer_id = await _create_customer(client, headers, await _create_origin(client, headers))
    response = await client.post(
        "/api/v1/lawsuits",
        json={
            "user_id": str(seeded.user_id),
            "lawsuit_type_id": lawsuit_type.json()["id"],
            "stage_id": stage_id,
            "parties": [{"customer_id": customer_id, "pole": "ATIVO", "is_client": True}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    result: str = response.json()["id"]
    return result


async def _create_category(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        "/api/v1/financial-categories",
        json={"name": f"Categoria {uuid.uuid4().hex[:8]}", "type": "RECEITA", "dre_group_id": 1},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    result: str = response.json()["id"]
    return result


async def _create_cost_center(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        "/api/v1/cost-centers", json={"name": f"Centro {uuid.uuid4().hex[:8]}"}, headers=headers
    )
    assert response.status_code == 201, response.text
    result: str = response.json()["id"]
    return result


async def _create_account(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        "/api/v1/bank-accounts",
        json={"kind": "CORRENTE", "name": f"Conta {uuid.uuid4().hex[:8]}", "initial_amount": "0"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    result: str = response.json()["id"]
    return result


async def _create_transaction(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    category_id: str,
    cost_center_id: str,
    account_id: str,
) -> str:
    response = await client.post(
        "/api/v1/transactions",
        json={
            "kind": "RECEITA",
            "debit_account_id": account_id,
            "category_id": category_id,
            "cost_center_id": cost_center_id,
            "amount": "10.00",
            "due_date": "2026-08-20",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    result: str = response.json()["id"]
    return result


async def test_etapa_de_a_nao_ve_processo_de_b(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regras 1-2: a etapa de A é excluível mesmo com B tendo processos — `usage_count`
    não pode enxergar linha de outro tenant."""
    (_a, headers_a), (b, headers_b) = await _two_tenants(make_user)
    stage_b = await _create_stage(client, headers_b)
    await _create_lawsuit(client, headers_b, b, stage_b)
    stage_a = await _create_stage(client, headers_a)

    assert (await client.delete(f"/api/v1/stages/{stage_a}", headers=headers_a)).status_code == 204


async def test_transferencia_de_etapa_nao_cruza_tenant(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """A etapa de B não é alvo válido para o transfer de A (o get_by_id do validador já
    não a enxerga) e o processo de B continua onde estava."""
    (a, headers_a), (b, headers_b) = await _two_tenants(make_user)
    stage_b = await _create_stage(client, headers_b)
    await _create_lawsuit(client, headers_b, b, stage_b)
    origem_a = await _create_stage(client, headers_a)
    await _create_lawsuit(client, headers_a, a, origem_a)

    cruzado = await client.post(
        "/api/v1/stages/transfer",
        json={"from_id": origem_a, "to_id": stage_b},
        headers=headers_a,
    )
    assert cruzado.status_code == 422

    destino_a = await _create_stage(client, headers_a)
    proprio = await client.post(
        "/api/v1/stages/transfer",
        json={"from_id": origem_a, "to_id": destino_a},
        headers=headers_a,
    )
    assert proprio.status_code == 200
    # Exatamente o processo de A — o de B não entrou na conta.
    assert proprio.json()["transferred_count"] == 1


async def test_origem_de_a_nao_ve_contato_de_b(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regras 3-4."""
    (_a, headers_a), (_b, headers_b) = await _two_tenants(make_user)
    origin_b = await _create_origin(client, headers_b)
    await _create_customer(client, headers_b, origin_b)
    origin_a = await _create_origin(client, headers_a)

    excluida = await client.delete(f"/api/v1/customer-origins/{origin_a}", headers=headers_a)
    assert excluida.status_code == 204


async def test_transferencia_de_origem_nao_cruza_tenant(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    (_a, headers_a), (_b, headers_b) = await _two_tenants(make_user)
    origin_b = await _create_origin(client, headers_b)
    await _create_customer(client, headers_b, origin_b)
    origem_a = await _create_origin(client, headers_a)
    await _create_customer(client, headers_a, origem_a)
    destino_a = await _create_origin(client, headers_a)

    transfer = await client.post(
        "/api/v1/customer-origins/transfer",
        json={"from_id": origem_a, "to_id": destino_a},
        headers=headers_a,
    )

    assert transfer.status_code == 200
    assert transfer.json()["transferred_count"] == 1


async def test_categoria_e_centro_de_a_nao_veem_lancamento_de_b(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regras 7-8: o lançamento de B não segura a categoria nem o centro de A."""
    (_a, headers_a), (_b, headers_b) = await _two_tenants(make_user)
    await _create_transaction(
        client,
        headers_b,
        category_id=await _create_category(client, headers_b),
        cost_center_id=await _create_cost_center(client, headers_b),
        account_id=await _create_account(client, headers_b),
    )
    category_a = await _create_category(client, headers_a)
    cost_center_a = await _create_cost_center(client, headers_a)

    assert (
        await client.delete(f"/api/v1/financial-categories/{category_a}", headers=headers_a)
    ).status_code == 204
    assert (
        await client.delete(f"/api/v1/cost-centers/{cost_center_a}", headers=headers_a)
    ).status_code == 204


async def test_conta_de_a_nao_ve_lancamento_de_b(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regras 9/11: o lançamento de B não entra no saldo nem na guarda de exclusão de A."""
    (_a, headers_a), (_b, headers_b) = await _two_tenants(make_user)
    await _create_transaction(
        client,
        headers_b,
        category_id=await _create_category(client, headers_b),
        cost_center_id=await _create_cost_center(client, headers_b),
        account_id=await _create_account(client, headers_b),
    )
    account_a = await _create_account(client, headers_a)

    saldo = await client.get(f"/api/v1/bank-accounts/{account_a}/balance", headers=headers_a)
    assert Decimal(str(saldo.json()["balance"])) == Decimal(0)

    excluida = await client.delete(f"/api/v1/bank-accounts/{account_a}", headers=headers_a)
    assert excluida.status_code == 204
