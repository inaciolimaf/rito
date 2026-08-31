"""Financeiro: plano de contas (spec 054, §8) — grupos DRE somente leitura, CRUD de
categorias e centros de custo, proteção do que é semeado, dupla dimensão de permissão
(financial_access × role) e isolamento por tenant."""

import uuid
from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.core.tokens import create_access_token
from app.domain.users.models import FinancialAccess, UserRole
from tests.integration.conftest import SeededUser

SessionFactory = async_sessionmaker[AsyncSession]


def _auth_header(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)
    return {"Authorization": f"Bearer {token}"}


async def _seed_default_row(
    app_session_factory: SessionFactory, tenant_id: uuid.UUID
) -> tuple[str, str]:
    """Backfill direto no banco (a migration só semeia tenants que já existiam quando
    rodou — ver Descobertas) de UMA categoria `is_default` e do centro `GERAL`, pra
    testar a proteção de exclusão contra dado real."""
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        category_id = (
            await session.execute(
                text(
                    "INSERT INTO financial_categories "
                    "(tenant_id, dre_group_id, name, type, is_default) "
                    "VALUES (:tenant_id, 1, 'HONORÁRIOS INICIAIS', 'RECEITA', true) "
                    "RETURNING id"
                ),
                {"tenant_id": tenant_id},
            )
        ).scalar_one()
        cost_center_id = (
            await session.execute(
                text(
                    "INSERT INTO cost_centers (tenant_id, name, is_default) "
                    "VALUES (:tenant_id, 'GERAL', true) RETURNING id"
                ),
                {"tenant_id": tenant_id},
            )
        ).scalar_one()
    return str(category_id), str(cost_center_id)


async def test_grupos_dre_sao_somente_leitura(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.READ_ONLY)
    headers = _auth_header(gestor)

    response = await client.get("/api/v1/dre-groups", headers=headers)
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 10
    assert {item["id"] for item in items} == set(range(10))
    assert next(item for item in items if item["id"] == 1)["nature"] == "RECEITA"

    post_response = await client.post("/api/v1/dre-groups", json={}, headers=headers)
    assert post_response.status_code == 405


async def test_crud_de_categorias_e_centros(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    headers = _auth_header(gestor)

    create_category = await client.post(
        "/api/v1/financial-categories",
        json={"name": "Categoria Nova", "type": "DESPESA", "dre_group_id": 6},
        headers=headers,
    )
    assert create_category.status_code == 201, create_category.text
    category = create_category.json()
    assert category["dre_group_name"] == "Despesas variáveis"
    assert category["is_default"] is False

    update_category = await client.put(
        f"/api/v1/financial-categories/{category['id']}",
        json={"name": "Categoria Renomeada", "type": "DESPESA", "dre_group_id": 7},
        headers=headers,
    )
    assert update_category.status_code == 200, update_category.text
    assert update_category.json()["name"] == "Categoria Renomeada"
    assert update_category.json()["dre_group_name"] == "Despesas bancárias"

    list_categories = await client.get("/api/v1/financial-categories", headers=headers)
    assert list_categories.status_code == 200
    assert category["id"] in {item["id"] for item in list_categories.json()["items"]}

    delete_category = await client.delete(
        f"/api/v1/financial-categories/{category['id']}", headers=headers
    )
    assert delete_category.status_code == 204

    create_cost_center = await client.post(
        "/api/v1/cost-centers", json={"name": "Filial Centro"}, headers=headers
    )
    assert create_cost_center.status_code == 201, create_cost_center.text
    cost_center = create_cost_center.json()
    assert cost_center["is_default"] is False

    update_cost_center = await client.put(
        f"/api/v1/cost-centers/{cost_center['id']}",
        json={"name": "Filial Zona Sul", "is_active": True},
        headers=headers,
    )
    assert update_cost_center.status_code == 200
    assert update_cost_center.json()["name"] == "Filial Zona Sul"

    delete_cost_center = await client.delete(
        f"/api/v1/cost-centers/{cost_center['id']}", headers=headers
    )
    assert delete_cost_center.status_code == 204


async def test_categoria_padrao_nao_e_excluivel(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: SessionFactory,
) -> None:
    gestor = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    headers = _auth_header(gestor)
    category_id, _cost_center_id = await _seed_default_row(app_session_factory, gestor.tenant_id)

    delete_response = await client.delete(
        f"/api/v1/financial-categories/{category_id}", headers=headers
    )
    assert delete_response.status_code == 409

    # Regra 3: "só inativada" — o PUT continua funcionando.
    inactivate = await client.put(
        f"/api/v1/financial-categories/{category_id}",
        json={
            "name": "HONORÁRIOS INICIAIS",
            "type": "RECEITA",
            "dre_group_id": 1,
            "is_active": False,
        },
        headers=headers,
    )
    assert inactivate.status_code == 200
    assert inactivate.json()["is_active"] is False


async def test_centro_geral_nao_e_excluivel_e_transferencia_funciona(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: SessionFactory,
) -> None:
    gestor = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    headers = _auth_header(gestor)
    _category_id, cost_center_id = await _seed_default_row(app_session_factory, gestor.tenant_id)

    delete_response = await client.delete(f"/api/v1/cost-centers/{cost_center_id}", headers=headers)
    assert delete_response.status_code == 409

    # Regra 4: transferência antes de excluir — validação real, reatribuição é no-op
    # documentado (nada referencia cost_centers ainda, ver Descobertas).
    other = await client.post(
        "/api/v1/cost-centers", json={"name": "Outro Centro"}, headers=headers
    )
    assert other.status_code == 201
    transfer = await client.post(
        "/api/v1/cost-centers/transfer",
        json={"from_id": other.json()["id"], "to_id": cost_center_id},
        headers=headers,
    )
    assert transfer.status_code == 200
    assert transfer.json()["transferred_count"] == 0

    invalid_transfer = await client.post(
        "/api/v1/cost-centers/transfer",
        json={"from_id": cost_center_id, "to_id": cost_center_id},
        headers=headers,
    )
    assert invalid_transfer.status_code == 422


async def test_financial_access_none_recebe_403_na_leitura(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.NONE)
    headers = _auth_header(gestor)

    for path in ("/api/v1/dre-groups", "/api/v1/financial-categories", "/api/v1/cost-centers"):
        response = await client.get(path, headers=headers)
        assert response.status_code == 403, path


async def test_read_only_le_mas_nao_escreve(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.READ_ONLY)
    headers = _auth_header(gestor)

    read_response = await client.get("/api/v1/financial-categories", headers=headers)
    assert read_response.status_code == 200

    write_category = await client.post(
        "/api/v1/financial-categories",
        json={"name": "Sem Acesso", "type": "DESPESA", "dre_group_id": 6},
        headers=headers,
    )
    assert write_category.status_code == 403

    write_cost_center = await client.post(
        "/api/v1/cost-centers", json={"name": "Sem Acesso"}, headers=headers
    )
    assert write_cost_center.status_code == 403


async def test_colaborador_com_full_cria_centro_de_custo(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    colaborador = await make_user(role=UserRole.COLABORADOR, financial_access=FinancialAccess.FULL)
    headers = _auth_header(colaborador)

    response = await client.post(
        "/api/v1/cost-centers", json={"name": "Centro do Colaborador"}, headers=headers
    )
    assert response.status_code == 201, response.text


async def test_colaborador_com_full_nao_cria_categoria(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    colaborador = await make_user(role=UserRole.COLABORADOR, financial_access=FinancialAccess.FULL)
    headers = _auth_header(colaborador)

    response = await client.post(
        "/api/v1/financial-categories",
        json={"name": "Categoria do Colaborador", "type": "DESPESA", "dre_group_id": 6},
        headers=headers,
    )
    assert response.status_code == 403


async def test_tenant_a_nao_ve_categoria_nem_centro_de_tenant_b(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    tenant_a = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    headers_a = _auth_header(tenant_a)
    category = await client.post(
        "/api/v1/financial-categories",
        json={"name": "Categoria A", "type": "DESPESA", "dre_group_id": 6},
        headers=headers_a,
    )
    assert category.status_code == 201
    cost_center = await client.post(
        "/api/v1/cost-centers", json={"name": "Centro A"}, headers=headers_a
    )
    assert cost_center.status_code == 201

    tenant_b = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    headers_b = _auth_header(tenant_b)

    categories_b = await client.get("/api/v1/financial-categories", headers=headers_b)
    assert category.json()["id"] not in {item["id"] for item in categories_b.json()["items"]}

    cost_centers_b = await client.get("/api/v1/cost-centers", headers=headers_b)
    assert cost_center.json()["id"] not in {item["id"] for item in cost_centers_b.json()["items"]}

    update_attempt = await client.put(
        f"/api/v1/financial-categories/{category.json()['id']}",
        json={"name": "Sequestro", "type": "DESPESA", "dre_group_id": 6},
        headers=headers_b,
    )
    assert update_attempt.status_code == 404


async def _make_full(
    make_user: Callable[..., Awaitable[SeededUser]],
) -> tuple[SeededUser, dict[str, str]]:
    gestor = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    return gestor, _auth_header(gestor)


async def _create_category(client: AsyncClient, headers: dict[str, str], *, type_: str) -> str:
    response = await client.post(
        "/api/v1/financial-categories",
        json={
            "name": f"Categoria {uuid.uuid4().hex[:8]}",
            "type": type_,
            "dre_group_id": 1 if type_ == "RECEITA" else 6,
        },
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


async def _create_transaction(
    client: AsyncClient, headers: dict[str, str], *, category_id: str, cost_center_id: str
) -> str:
    account = await client.post(
        "/api/v1/bank-accounts",
        json={"kind": "CORRENTE", "name": f"Conta {uuid.uuid4().hex[:8]}", "initial_amount": "0"},
        headers=headers,
    )
    assert account.status_code == 201, account.text
    response = await client.post(
        "/api/v1/transactions",
        json={
            "kind": "RECEITA",
            "debit_account_id": account.json()["id"],
            "category_id": category_id,
            "cost_center_id": cost_center_id,
            "amount": "42.00",
            "due_date": "2026-08-20",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    result: str = response.json()["id"]
    return result


async def _transaction_row(
    client: AsyncClient, headers: dict[str, str], transaction_id: str
) -> dict[str, object]:
    """Não há GET /transactions/{id} — a listagem é o único jeito de reler um lançamento."""
    response = await client.get("/api/v1/transactions", headers=headers)
    assert response.status_code == 200, response.text
    return next(item for item in response.json()["items"] if item["id"] == transaction_id)


async def _category_of(client: AsyncClient, headers: dict[str, str], transaction_id: str) -> object:
    return (await _transaction_row(client, headers, transaction_id))["category_id"]


async def _cost_center_of(
    client: AsyncClient, headers: dict[str, str], transaction_id: str
) -> object:
    return (await _transaction_row(client, headers, transaction_id))["cost_center_id"]


async def test_excluir_categoria_em_uso_retorna_409_e_transferencia_libera(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Spec 101, regras 7-8 (metade da dívida nº 20). Antes desta spec o DELETE violava a
    FK `transactions.category_id` e o transfer devolvia sempre 0."""
    _gestor, headers = await _make_full(make_user)
    origem = await _create_category(client, headers, type_="RECEITA")
    destino = await _create_category(client, headers, type_="RECEITA")
    cost_center_id = await _create_cost_center(client, headers)
    transaction_id = await _create_transaction(
        client, headers, category_id=origem, cost_center_id=cost_center_id
    )

    bloqueada = await client.delete(f"/api/v1/financial-categories/{origem}", headers=headers)
    assert bloqueada.status_code == 409
    assert "transfira" in bloqueada.json()["detail"].lower()

    transfer = await client.post(
        "/api/v1/financial-categories/transfer",
        json={"from_id": origem, "to_id": destino},
        headers=headers,
    )
    assert transfer.status_code == 200
    assert transfer.json()["transferred_count"] == 1

    assert await _category_of(client, headers, transaction_id) == destino

    liberada = await client.delete(f"/api/v1/financial-categories/{origem}", headers=headers)
    assert liberada.status_code == 204


async def test_excluir_centro_de_custo_em_uso_retorna_409_e_transferencia_libera(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Spec 101, regras 7-8 sobre `transactions.cost_center_id`."""
    _gestor, headers = await _make_full(make_user)
    origem = await _create_cost_center(client, headers)
    destino = await _create_cost_center(client, headers)
    category_id = await _create_category(client, headers, type_="RECEITA")
    transaction_id = await _create_transaction(
        client, headers, category_id=category_id, cost_center_id=origem
    )

    bloqueado = await client.delete(f"/api/v1/cost-centers/{origem}", headers=headers)
    assert bloqueado.status_code == 409

    transfer = await client.post(
        "/api/v1/cost-centers/transfer",
        json={"from_id": origem, "to_id": destino},
        headers=headers,
    )
    assert transfer.status_code == 200
    assert transfer.json()["transferred_count"] == 1

    assert await _cost_center_of(client, headers, transaction_id) == destino

    liberado = await client.delete(f"/api/v1/cost-centers/{origem}", headers=headers)
    assert liberado.status_code == 204
