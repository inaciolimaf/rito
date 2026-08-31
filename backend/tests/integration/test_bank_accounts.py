"""Financeiro: contas e cartões (spec 055, §8) — CRUD dos 5 tipos, constraints de
ciclo/vencimento do cartão, unicidade da conta padrão (aplicação + banco), inativar
padrão sem substituta e isolamento por tenant.

Regras 3/4/6/9 (saldo real, fatura, "conta em uso" e imutabilidade do saldo inicial)
dependiam de lançamentos e ficaram como stub até a spec 101, que fez o retrofit e
fechou a dívida nº 20 — daqui em diante o saldo é o saldo, conta com lançamento não é
excluível e `initial_amount` trava depois do 1º lançamento (regras 9-12 da 101).
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.core.tokens import create_access_token
from app.domain.users.models import FinancialAccess, UserRole
from tests.integration.conftest import SeededUser

SessionFactory = async_sessionmaker[AsyncSession]


def _auth_header(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)
    return {"Authorization": f"Bearer {token}"}


async def _make_gestor_full(
    make_user: Callable[..., Awaitable[SeededUser]],
) -> tuple[SeededUser, dict[str, str]]:
    gestor = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    return gestor, _auth_header(gestor)


async def _create_account(
    client: AsyncClient, headers: dict[str, str], **overrides: object
) -> dict[str, object]:
    payload: dict[str, object] = {
        "kind": "CORRENTE",
        "name": f"Conta {uuid.uuid4().hex[:8]}",
        "initial_amount": "0",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/bank-accounts", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    result: dict[str, object] = response.json()
    return result


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


async def _create_movement(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    kind: str,
    account_id: str,
    amount: str,
    pay: bool = False,
    due_date: str | None = None,
    **extra: object,
) -> str:
    """Lançamento vinculado à conta. `pay=True` dá baixa hoje — só o pago entra no saldo
    (regra 9 da 101)."""
    payload: dict[str, object] = {
        "kind": kind,
        "debit_account_id": account_id,
        "category_id": await _create_category(client, headers, type_=kind),
        "cost_center_id": await _create_cost_center(client, headers),
        "amount": amount,
        "due_date": due_date or date.today().isoformat(),
    }
    payload.update(extra)
    response = await client.post("/api/v1/transactions", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    transaction_id: str = response.json()["id"]

    if pay:
        paid = await client.post(
            f"/api/v1/transactions/{transaction_id}/pay",
            json={"payment_date": date.today().isoformat()},
            headers=headers,
        )
        assert paid.status_code == 200, paid.text
    return transaction_id


async def _create_receita(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    account_id: str,
    amount: str,
    pay: bool = False,
    due_date: str | None = None,
    **extra: object,
) -> str:
    return await _create_movement(
        client,
        headers,
        kind="RECEITA",
        account_id=account_id,
        amount=amount,
        pay=pay,
        due_date=due_date,
        **extra,
    )


async def _create_despesa(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    account_id: str,
    amount: str,
    pay: bool = False,
    due_date: str | None = None,
    **extra: object,
) -> str:
    return await _create_movement(
        client,
        headers,
        kind="DESPESA",
        account_id=account_id,
        amount=amount,
        pay=pay,
        due_date=due_date,
        **extra,
    )


async def test_crud_dos_5_tipos(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)

    for kind in ("CORRENTE", "POUPANCA", "INVESTIMENTO", "OUTRO"):
        account = await _create_account(client, headers, kind=kind)
        assert account["kind"] == kind
        assert account["cycle_day"] is None

    card = await _create_account(client, headers, kind="CARTAO_CREDITO", cycle_day=10, due_day=20)
    assert card["cycle_day"] == 10
    assert card["due_day"] == 20

    update = await client.put(
        f"/api/v1/bank-accounts/{card['id']}",
        json={
            "kind": "CARTAO_CREDITO",
            "name": "Cartão Renomeado",
            "cycle_day": 15,
            "due_day": 25,
            "initial_amount": "0",
            "is_active": True,
        },
        headers=headers,
    )
    assert update.status_code == 200, update.text
    assert update.json()["name"] == "Cartão Renomeado"
    assert update.json()["cycle_day"] == 15

    listing = await client.get("/api/v1/bank-accounts", headers=headers)
    assert listing.status_code == 200
    assert card["id"] in {item["id"] for item in listing.json()["items"]}

    delete = await client.delete(f"/api/v1/bank-accounts/{card['id']}", headers=headers)
    assert delete.status_code == 204


async def test_cartao_sem_ciclo_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)

    response = await client.post(
        "/api/v1/bank-accounts",
        json={"kind": "CARTAO_CREDITO", "name": "Cartão Incompleto", "initial_amount": "0"},
        headers=headers,
    )
    assert response.status_code == 422


async def test_conta_corrente_com_ciclo_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)

    response = await client.post(
        "/api/v1/bank-accounts",
        json={
            "kind": "CORRENTE",
            "name": "Conta Com Ciclo",
            "cycle_day": 10,
            "due_day": 20,
            "initial_amount": "0",
        },
        headers=headers,
    )
    assert response.status_code == 422


async def test_so_uma_padrao_ativa_mesmo_tentando_burlar_pelo_banco(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: SessionFactory,
) -> None:
    """Regra 2: a aplicação nunca deixa 2 defaults (testado abaixo), mas o índice
    único parcial é quem garante de verdade — direto no banco, sem passar pela
    aplicação, a segunda tentativa tem que falhar."""
    gestor, headers = await _make_gestor_full(make_user)
    first = await _create_account(client, headers, is_default=True)
    assert first["is_default"] is True

    with pytest.raises(IntegrityError):
        async with app_session_factory() as session, session.begin():
            await set_tenant_context(session, gestor.tenant_id)
            await session.execute(
                text(
                    "INSERT INTO bank_accounts (tenant_id, kind, name, initial_amount, is_default) "
                    "VALUES (:tenant_id, 'CORRENTE', 'Segunda Padrão', 0, true)"
                ),
                {"tenant_id": gestor.tenant_id},
            )


async def test_trocar_padrao_desmarca_a_anterior(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    first = await _create_account(client, headers, is_default=True)
    second = await _create_account(client, headers)

    set_default = await client.post(
        f"/api/v1/bank-accounts/{second['id']}/set-default", headers=headers
    )
    assert set_default.status_code == 200
    assert set_default.json()["is_default"] is True

    listing = await client.get("/api/v1/bank-accounts", headers=headers)
    by_id = {item["id"]: item for item in listing.json()["items"]}
    assert by_id[first["id"]]["is_default"] is False
    assert by_id[second["id"]]["is_default"] is True


async def test_inativar_padrao_sem_substituta_retorna_409(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    account = await _create_account(client, headers, is_default=True)

    response = await client.put(
        f"/api/v1/bank-accounts/{account['id']}",
        json={
            "kind": "CORRENTE",
            "name": account["name"],
            "initial_amount": "0",
            "is_active": False,
        },
        headers=headers,
    )
    assert response.status_code == 409


async def test_excluir_conta_sem_lancamento_continua_204(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Spec 101, regra 11: a guarda não muda o caminho feliz."""
    _gestor, headers = await _make_gestor_full(make_user)
    account = await _create_account(client, headers)

    response = await client.delete(f"/api/v1/bank-accounts/{account['id']}", headers=headers)
    assert response.status_code == 204


async def test_excluir_conta_com_lancamento_retorna_409(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Spec 101, regra 11 — antes desta spec o DELETE violava a FK e virava 500."""
    _gestor, headers = await _make_gestor_full(make_user)
    account = await _create_account(client, headers)
    await _create_receita(client, headers, account_id=str(account["id"]), amount="10.00")

    response = await client.delete(f"/api/v1/bank-accounts/{account['id']}", headers=headers)

    assert response.status_code == 409
    assert "lançamento" in response.json()["detail"].lower()


async def test_saldo_inicial_trava_depois_do_primeiro_lancamento(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Spec 101, regra 12: mudar o saldo inicial reescreveria retroativamente todo saldo
    já calculado. Reenviar o MESMO valor continua passando — um PUT que não mexe no
    campo não é uma mudança."""
    _gestor, headers = await _make_gestor_full(make_user)
    account = await _create_account(client, headers, initial_amount="100.00")
    account_id = str(account["id"])

    # Sem lançamento ainda: editar é livre.
    livre = await client.put(
        f"/api/v1/bank-accounts/{account_id}",
        json={"kind": "CORRENTE", "name": str(account["name"]), "initial_amount": "250.00"},
        headers=headers,
    )
    assert livre.status_code == 200

    await _create_receita(client, headers, account_id=account_id, amount="10.00")

    travado = await client.put(
        f"/api/v1/bank-accounts/{account_id}",
        json={"kind": "CORRENTE", "name": str(account["name"]), "initial_amount": "999.00"},
        headers=headers,
    )
    assert travado.status_code == 409

    mesmo_valor = await client.put(
        f"/api/v1/bank-accounts/{account_id}",
        json={"kind": "CORRENTE", "name": str(account["name"]), "initial_amount": "250.00"},
        headers=headers,
    )
    assert mesmo_valor.status_code == 200


async def test_saldo_soma_pagos_e_ignora_aberto_e_interno(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Spec 101, regra 9: saldo = inicial + entradas pagas − saídas pagas, com
    `is_internal` de fora (regra 1 da 058) e o que não foi pago também."""
    _gestor, headers = await _make_gestor_full(make_user)
    account = await _create_account(client, headers, initial_amount="100.00")
    account_id = str(account["id"])

    await _create_receita(client, headers, account_id=account_id, amount="50.00", pay=True)
    await _create_despesa(client, headers, account_id=account_id, amount="20.00", pay=True)
    # Em aberto: não entra no saldo.
    await _create_receita(client, headers, account_id=account_id, amount="777.00")
    # Interno e pago: também não entra (regra 1 da spec 058).
    await _create_receita(
        client, headers, account_id=account_id, amount="888.00", pay=True, is_internal=True
    )

    response = await client.get(f"/api/v1/bank-accounts/{account_id}/balance", headers=headers)

    assert response.status_code == 200
    assert Decimal(response.json()["balance"]) == Decimal("130.00")


async def test_saldo_de_cartao_de_credito_devolve_a_fatura_do_ciclo(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Spec 101, regra 10: cartão não tem saldo, tem fatura do ciclo corrente — a mesma
    conta que `/bank-accounts/balances` já marcava com `is_invoice`."""
    _gestor, headers = await _make_gestor_full(make_user)
    hoje = date.today()
    account = await _create_account(
        client,
        headers,
        kind="CARTAO_CREDITO",
        initial_amount="0",
        cycle_day=1,
        due_day=10,
    )
    account_id = str(account["id"])
    # Despesa vencendo hoje cai no ciclo corrente (cycle_day=1), paga ou não.
    await _create_despesa(
        client, headers, account_id=account_id, amount="70.00", due_date=hoje.isoformat()
    )

    response = await client.get(f"/api/v1/bank-accounts/{account_id}/balance", headers=headers)

    assert response.status_code == 200
    assert Decimal(response.json()["balance"]) == Decimal("70.00")


async def test_saldo_devolve_o_saldo_inicial_por_enquanto(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regras 3/4 completas na spec 056 — sem lançamentos, o saldo é só o inicial."""
    _gestor, headers = await _make_gestor_full(make_user)
    account = await _create_account(client, headers, initial_amount="1500.75")

    response = await client.get(f"/api/v1/bank-accounts/{account['id']}/balance", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["balance"] == 1500.75


async def test_financial_institutions_busca_por_nome(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    colaborador = await make_user(role=UserRole.COLABORADOR)
    headers = _auth_header(colaborador)

    response = await client.get(
        "/api/v1/financial-institutions", params={"q": "ITAÚ"}, headers=headers
    )
    assert response.status_code == 200
    names = [item["name"] for item in response.json()["items"]]
    assert any("ITA" in name for name in names)


async def test_escrita_exige_financial_access_full(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.READ_ONLY)
    headers = _auth_header(gestor)

    response = await client.post(
        "/api/v1/bank-accounts",
        json={"kind": "CORRENTE", "name": "Sem Acesso", "initial_amount": "0"},
        headers=headers,
    )
    assert response.status_code == 403


async def test_tenant_a_nao_ve_conta_de_tenant_b(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor_a, headers_a = await _make_gestor_full(make_user)
    account = await _create_account(client, headers_a)

    gestor_b, headers_b = await _make_gestor_full(make_user)
    listing_b = await client.get("/api/v1/bank-accounts", headers=headers_b)
    assert account["id"] not in {item["id"] for item in listing_b.json()["items"]}

    update_attempt = await client.put(
        f"/api/v1/bank-accounts/{account['id']}",
        json={
            "kind": "CORRENTE",
            "name": "Sequestro",
            "initial_amount": "0",
            "is_active": True,
        },
        headers=headers_b,
    )
    assert update_attempt.status_code == 404
