"""Financeiro: lançamentos (spec 056, §8) — os 3 tipos, regra 1 (tipo × categoria) nos
dois sentidos, formato de transferência, vínculo com processo, normalizações
(descrição/competência), baixa/estorno, exclusão de pago, permissão e isolamento por
tenant."""

import uuid
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.users.models import FinancialAccess, UserRole
from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuits import (
    _auth_header,
    _create_customer,
    _create_lawsuit,
    _create_lawsuit_type,
    _create_stage,
)


async def _make_gestor_full(
    make_user: Callable[..., Awaitable[SeededUser]],
) -> tuple[SeededUser, dict[str, str]]:
    gestor = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    return gestor, _auth_header(gestor)


async def _create_category(
    client: AsyncClient, headers: dict[str, str], *, type_: str, dre_group_id: int = 6
) -> str:
    response = await client.post(
        "/api/v1/financial-categories",
        json={
            "name": f"Categoria {uuid.uuid4().hex[:8]}",
            "type": type_,
            "dre_group_id": dre_group_id,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    result: str = response.json()["id"]
    return result


async def _create_cost_center(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        "/api/v1/cost-centers",
        json={"name": f"Centro {uuid.uuid4().hex[:8]}"},
        headers=headers,
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


async def _fixtures(client: AsyncClient, headers: dict[str, str]) -> tuple[str, str, str, str, str]:
    """(receita_category_id, despesa_category_id, cost_center_id, account_a_id, account_b_id)."""
    receita_id = await _create_category(client, headers, type_="RECEITA", dre_group_id=1)
    despesa_id = await _create_category(client, headers, type_="DESPESA", dre_group_id=6)
    cost_center_id = await _create_cost_center(client, headers)
    account_a = await _create_account(client, headers)
    account_b = await _create_account(client, headers)
    return receita_id, despesa_id, cost_center_id, account_a, account_b


def _receita_payload(
    *, category_id: str, cost_center_id: str, account_id: str, **extra: object
) -> dict[str, object]:
    payload: dict[str, object] = {
        "kind": "RECEITA",
        "debit_account_id": account_id,
        "category_id": category_id,
        "cost_center_id": cost_center_id,
        "amount": "150.00",
        "due_date": "2026-08-20",
    }
    payload.update(extra)
    return payload


async def test_criar_receita_despesa_e_transferencia(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    receita_id, despesa_id, cost_center_id, account_a, account_b = await _fixtures(client, headers)

    receita = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id, cost_center_id=cost_center_id, account_id=account_a
        ),
        headers=headers,
    )
    assert receita.status_code == 201, receita.text
    assert receita.json()["kind"] == "RECEITA"
    assert receita.json()["competence"] == "2026-08-01"

    despesa = await client.post(
        "/api/v1/transactions",
        json={
            "kind": "DESPESA",
            "debit_account_id": account_a,
            "category_id": despesa_id,
            "cost_center_id": cost_center_id,
            "amount": "80.00",
            "due_date": "2026-08-21",
        },
        headers=headers,
    )
    assert despesa.status_code == 201, despesa.text
    assert despesa.json()["kind"] == "DESPESA"

    transferencia = await client.post(
        "/api/v1/transactions",
        json={
            "kind": "TRANSFERENCIA",
            "debit_account_id": account_a,
            "credit_account_id": account_b,
            "amount": "50.00",
            "due_date": "2026-08-22",
        },
        headers=headers,
    )
    assert transferencia.status_code == 201, transferencia.text
    body = transferencia.json()
    assert body["kind"] == "TRANSFERENCIA"
    assert body["debit_account_id"] == account_a
    assert body["credit_account_id"] == account_b
    assert body["category_id"] is None


async def test_receita_com_categoria_de_despesa_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    _receita_id, despesa_id, cost_center_id, account_a, _account_b = await _fixtures(
        client, headers
    )

    response = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=despesa_id, cost_center_id=cost_center_id, account_id=account_a
        ),
        headers=headers,
    )
    assert response.status_code == 422


async def test_despesa_com_categoria_de_receita_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    receita_id, _despesa_id, cost_center_id, account_a, _account_b = await _fixtures(
        client, headers
    )

    response = await client.post(
        "/api/v1/transactions",
        json={
            "kind": "DESPESA",
            "debit_account_id": account_a,
            "category_id": receita_id,
            "cost_center_id": cost_center_id,
            "amount": "80.00",
            "due_date": "2026-08-21",
        },
        headers=headers,
    )
    assert response.status_code == 422


async def test_transferencia_com_contas_iguais_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    _r, _d, _cc, account_a, _b = await _fixtures(client, headers)

    response = await client.post(
        "/api/v1/transactions",
        json={
            "kind": "TRANSFERENCIA",
            "debit_account_id": account_a,
            "credit_account_id": account_a,
            "amount": "50.00",
            "due_date": "2026-08-22",
        },
        headers=headers,
    )
    assert response.status_code == 422


async def test_transferencia_com_categoria_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    receita_id, _d, cost_center_id, account_a, account_b = await _fixtures(client, headers)

    response = await client.post(
        "/api/v1/transactions",
        json={
            "kind": "TRANSFERENCIA",
            "debit_account_id": account_a,
            "credit_account_id": account_b,
            "category_id": receita_id,
            "cost_center_id": cost_center_id,
            "amount": "50.00",
            "due_date": "2026-08-22",
        },
        headers=headers,
    )
    assert response.status_code == 422


async def test_processo_sem_cliente_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor, headers = await _make_gestor_full(make_user)
    receita_id, _d, cost_center_id, account_a, _b = await _fixtures(client, headers)
    type_id, _group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    lawsuit = await _create_lawsuit(
        client, headers, user_id=str(gestor.user_id), lawsuit_type_id=type_id, stage_id=stage_id
    )

    response = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            lawsuit_id=lawsuit["id"],
        ),
        headers=headers,
    )
    assert response.status_code == 422


async def test_descricao_vira_maiusculas(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    receita_id, _d, cost_center_id, account_a, _b = await _fixtures(client, headers)

    response = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            description="honorários de êxito",
        ),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["description"] == "HONORÁRIOS DE ÊXITO"


async def test_competencia_derivada_do_vencimento(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    receita_id, _d, cost_center_id, account_a, _b = await _fixtures(client, headers)

    response = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            due_date="2026-08-31",
        ),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["competence"] == "2026-08-01"

    explicit = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            due_date="2026-08-31",
            competence="2026-09-01",
        ),
        headers=headers,
    )
    assert explicit.status_code == 201, explicit.text
    assert explicit.json()["competence"] == "2026-09-01"


async def test_amount_zero_ou_negativo_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    receita_id, _d, cost_center_id, account_a, _b = await _fixtures(client, headers)

    for amount in ("0", "-10.00"):
        response = await client.post(
            "/api/v1/transactions",
            json=_receita_payload(
                category_id=receita_id,
                cost_center_id=cost_center_id,
                account_id=account_a,
                amount=amount,
            ),
            headers=headers,
        )
        assert response.status_code == 422, amount


async def test_pagamento_futuro_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    receita_id, _d, cost_center_id, account_a, _b = await _fixtures(client, headers)
    amanha = (date.today() + timedelta(days=1)).isoformat()

    response = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            payment_date=amanha,
        ),
        headers=headers,
    )
    assert response.status_code == 422


async def test_baixa_e_estorno(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    receita_id, _d, cost_center_id, account_a, _b = await _fixtures(client, headers)

    created = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id, cost_center_id=cost_center_id, account_id=account_a
        ),
        headers=headers,
    )
    transaction_id = created.json()["id"]
    assert created.json()["payment_date"] is None

    pay = await client.post(
        f"/api/v1/transactions/{transaction_id}/pay",
        json={"payment_date": "2026-08-11"},
        headers=headers,
    )
    assert pay.status_code == 200, pay.text
    assert pay.json()["payment_date"] == "2026-08-11"

    unpay = await client.post(f"/api/v1/transactions/{transaction_id}/unpay", headers=headers)
    assert unpay.status_code == 200, unpay.text
    assert unpay.json()["payment_date"] is None


async def test_excluir_pago_retorna_409(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    receita_id, _d, cost_center_id, account_a, _b = await _fixtures(client, headers)

    created = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id, cost_center_id=cost_center_id, account_id=account_a
        ),
        headers=headers,
    )
    transaction_id = created.json()["id"]
    await client.post(
        f"/api/v1/transactions/{transaction_id}/pay",
        json={"payment_date": "2026-08-11"},
        headers=headers,
    )

    delete_response = await client.delete(f"/api/v1/transactions/{transaction_id}", headers=headers)
    assert delete_response.status_code == 409

    unpay = await client.post(f"/api/v1/transactions/{transaction_id}/unpay", headers=headers)
    assert unpay.status_code == 200
    delete_after_estorno = await client.delete(
        f"/api/v1/transactions/{transaction_id}", headers=headers
    )
    assert delete_after_estorno.status_code == 204


async def test_transferencia_nao_altera_saldo_hoje_deferido(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 9: transferência move saldo entre contas. O cálculo de saldo real a
    partir de lançamentos é dívida técnica consciente (ver `docs/DIVIDA-TECNICA.md`
    item 20) — `BankAccountService.get_balance` ainda devolve `initial_amount` sempre.
    Este teste documenta o estado ATUAL (saldo não muda), não o comportamento final;
    o que a 056 garante é que a transferência é *registrada* corretamente (contas de
    origem/destino diferentes, sem categoria), que é o que o retrofit vai consumir."""
    _gestor, headers = await _make_gestor_full(make_user)
    _r, _d, _cc, account_a, account_b = await _fixtures(client, headers)

    transferencia = await client.post(
        "/api/v1/transactions",
        json={
            "kind": "TRANSFERENCIA",
            "debit_account_id": account_a,
            "credit_account_id": account_b,
            "amount": "50.00",
            "due_date": "2026-08-22",
        },
        headers=headers,
    )
    assert transferencia.status_code == 201, transferencia.text

    balance_a = await client.get(f"/api/v1/bank-accounts/{account_a}/balance", headers=headers)
    balance_b = await client.get(f"/api/v1/bank-accounts/{account_b}/balance", headers=headers)
    assert balance_a.json()["balance"] == 0
    assert balance_b.json()["balance"] == 0


async def test_read_only_nao_escreve(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor_full = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    headers_full = _auth_header(gestor_full)
    receita_id, _d, cost_center_id, account_a, _b = await _fixtures(client, headers_full)

    read_only = await make_user(
        role=UserRole.GESTOR,
        financial_access=FinancialAccess.READ_ONLY,
        tenant_id=gestor_full.tenant_id,
    )
    headers_ro = _auth_header(read_only)

    list_response = await client.get("/api/v1/transactions", headers=headers_ro)
    assert list_response.status_code == 200

    write_response = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id, cost_center_id=cost_center_id, account_id=account_a
        ),
        headers=headers_ro,
    )
    assert write_response.status_code == 403


async def test_tenant_a_nao_ve_lancamento_de_tenant_b(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor_a, headers_a = await _make_gestor_full(make_user)
    receita_id, _d, cost_center_id, account_a, _b = await _fixtures(client, headers_a)
    created = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id, cost_center_id=cost_center_id, account_id=account_a
        ),
        headers=headers_a,
    )
    assert created.status_code == 201
    transaction_id = created.json()["id"]

    _gestor_b, headers_b = await _make_gestor_full(make_user)
    list_b = await client.get("/api/v1/transactions", headers=headers_b)
    assert transaction_id not in {item["id"] for item in list_b.json()["items"]}

    get_b = await client.put(
        f"/api/v1/transactions/{transaction_id}",
        json=_receita_payload(
            category_id=receita_id, cost_center_id=cost_center_id, account_id=account_a
        ),
        headers=headers_b,
    )
    assert get_b.status_code == 404


async def test_vinculo_com_processo_alimenta_painel_financeiro(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 11: lançamento vinculado a `lawsuit_id` aparece no
    `GET /lawsuits/{id}/financial-summary` — RECEITA paga soma `received`, RECEITA em
    aberto soma `to_receive`, DESPESA paga soma `expenses`."""
    gestor, headers = await _make_gestor_full(make_user)
    receita_id, despesa_id, cost_center_id, account_a, _b = await _fixtures(client, headers)
    type_id, _group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    customer_id = await _create_customer(client, headers, "Cliente do Processo")
    lawsuit = await _create_lawsuit(
        client,
        headers,
        user_id=str(gestor.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
        parties=[{"customer_id": customer_id, "pole": "ATIVO", "is_client": True}],
    )

    paid_receita = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            customer_id=customer_id,
            lawsuit_id=lawsuit["id"],
            amount="1000.00",
            payment_date="2026-08-10",
        ),
        headers=headers,
    )
    assert paid_receita.status_code == 201, paid_receita.text

    open_receita = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            customer_id=customer_id,
            lawsuit_id=lawsuit["id"],
            amount="300.00",
        ),
        headers=headers,
    )
    assert open_receita.status_code == 201, open_receita.text

    paid_despesa = await client.post(
        "/api/v1/transactions",
        json={
            "kind": "DESPESA",
            "debit_account_id": account_a,
            "category_id": despesa_id,
            "cost_center_id": cost_center_id,
            "customer_id": customer_id,
            "lawsuit_id": lawsuit["id"],
            "amount": "200.00",
            "due_date": "2026-08-20",
            "payment_date": "2026-08-10",
        },
        headers=headers,
    )
    assert paid_despesa.status_code == 201, paid_despesa.text

    summary = await client.get(
        f"/api/v1/lawsuits/{lawsuit['id']}/financial-summary", headers=headers
    )
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert body["received"] == 1000.00
    assert body["to_receive"] == 300.00
    assert body["expenses"] == 200.00
    assert body["net_result"] == 800.00


async def test_os_4_check_da_migration_barram_escrita_direta_no_banco(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Auditoria numérica (refatoração 060): as regras 2/3/6/7 (spec 056) são checadas
    nos dois lugares — Pydantic (422, sem round-trip) *e* os 4 CHECK da migration
    (defesa contra escrita direta no banco, mesma dupla camada da spec 055). Este
    teste só prova a segunda camada — a primeira já está coberta pelos testes de 422
    acima, que nunca chegam a exercitar o CHECK (Pydantic barra antes)."""
    gestor, headers = await _make_gestor_full(make_user)
    receita_id, _d, cost_center_id, account_a, account_b = await _fixtures(client, headers)
    type_id, _group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    lawsuit = await _create_lawsuit(
        client, headers, user_id=str(gestor.user_id), lawsuit_type_id=type_id, stage_id=stage_id
    )

    base = (
        "INSERT INTO transactions "
        "(tenant_id, kind, user_id, debit_account_id, credit_account_id, category_id, "
        "cost_center_id, customer_id, lawsuit_id, amount, due_date, payment_date, competence) "
        "VALUES (:tenant_id, :kind, :user_id, :debit_account_id, :credit_account_id, "
        ":category_id, :cost_center_id, :customer_id, :lawsuit_id, :amount, :due_date, "
        ":payment_date, :competence)"
    )
    valid_params: dict[str, object] = {
        "tenant_id": gestor.tenant_id,
        "kind": "RECEITA",
        "user_id": gestor.user_id,
        "debit_account_id": uuid.UUID(account_a),
        "credit_account_id": None,
        "category_id": uuid.UUID(receita_id),
        "cost_center_id": uuid.UUID(cost_center_id),
        "customer_id": None,
        "lawsuit_id": None,
        "amount": Decimal("10.00"),
        "due_date": date(2026, 8, 20),
        "payment_date": None,
        "competence": date(2026, 8, 1),
    }
    violations: dict[str, dict[str, object]] = {
        "ck_tx_amount_positive": {"amount": Decimal("-10.00")},
        "ck_tx_transfer_accounts": {
            "kind": "TRANSFERENCIA",
            "category_id": None,
            "cost_center_id": None,
            "credit_account_id": uuid.UUID(account_a),  # igual à origem
        },
        "ck_tx_lawsuit_needs_customer": {
            "lawsuit_id": uuid.UUID(str(lawsuit["id"])),
            "customer_id": None,
        },
        "ck_tx_payment_not_future": {"payment_date": date.today() + timedelta(days=1)},
    }
    for constraint_name, override in violations.items():
        params = {**valid_params, **override}
        with pytest.raises(IntegrityError, match=constraint_name):
            async with app_session_factory() as session, session.begin():
                await set_tenant_context(session, gestor.tenant_id)
                await session.execute(text(base), params)
