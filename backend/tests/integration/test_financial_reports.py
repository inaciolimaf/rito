"""Financeiro: relatórios DRE e DFC (spec 062, §8) — agregação por grupo DRE em
competência (DRE) e caixa (DFC), naturezas opostas dentro do mesmo grupo, exclusão de
transferência/interno, filtro por conta e isolamento por tenant."""

from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.core.tokens import create_access_token
from app.domain.users.models import FinancialAccess, UserRole
from tests.integration.conftest import SeededUser
from tests.integration.test_transactions import (
    _create_account,
    _create_category,
    _create_cost_center,
    _fixtures,
    _make_gestor_full,
    _receita_payload,
)


def _auth_header(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)
    return {"Authorization": f"Bearer {token}"}


async def _pay(
    client: AsyncClient, headers: dict[str, str], transaction_id: str, date_: str
) -> None:
    response = await client.post(
        f"/api/v1/transactions/{transaction_id}/pay",
        json={"payment_date": date_},
        headers=headers,
    )
    assert response.status_code == 200, response.text


async def _group_row(rows: list[dict[str, object]], group_id: int) -> dict[str, object] | None:
    return next((row for row in rows if row["dre_group_id"] == group_id), None)


async def test_dre_agrupa_por_grupo_e_bate_com_o_razao(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    receita_id, despesa_id, cost_center_id, account_a, _b = await _fixtures(client, headers)

    await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            amount="300.00",
            due_date="2026-08-10",
            competence="2026-08-01",
        ),
        headers=headers,
    )
    await client.post(
        "/api/v1/transactions",
        json={
            "kind": "DESPESA",
            "debit_account_id": account_a,
            "category_id": despesa_id,
            "cost_center_id": cost_center_id,
            "amount": "120.00",
            "due_date": "2026-08-15",
            "competence": "2026-08-01",
        },
        headers=headers,
    )

    response = await client.get(
        "/api/v1/financial-reports/dre",
        params={"from": "2026-08-01", "to": "2026-08-31"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()

    receita_row = await _group_row(body["rows"], 1)
    despesa_row = await _group_row(body["rows"], 6)
    assert receita_row is not None and receita_row["receita"] == 300.0
    assert despesa_row is not None and despesa_row["despesa"] == 120.0
    assert body["total_receita"] == 300.0
    assert body["total_despesa"] == 120.0
    assert body["resultado"] == 180.0


async def test_dfc_so_conta_lancamento_pago_por_payment_date(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    receita_id, _despesa_id, cost_center_id, account_a, _b = await _fixtures(client, headers)

    unpaid = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            amount="100.00",
            due_date="2026-08-10",
        ),
        headers=headers,
    )
    assert unpaid.status_code == 201, unpaid.text

    paid = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            amount="250.00",
            due_date="2026-07-28",
        ),
        headers=headers,
    )
    assert paid.status_code == 201, paid.text
    await _pay(client, headers, paid.json()["id"], "2026-08-05")

    response = await client.get(
        "/api/v1/financial-reports/dfc",
        params={"from": "2026-08-01", "to": "2026-08-31"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["total_receita"] == 250.0
    receita_row = await _group_row(body["rows"], 1)
    assert receita_row is not None and receita_row["receita"] == 250.0


async def test_grupo_com_naturezas_opostas_soma_liquido(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    cost_center_id = await _create_cost_center(client, headers)
    account_a = await _create_account(client, headers)
    # dre_group 6 é "Despesas variáveis" (natureza DESPESA) — categoria RECEITA nele
    # é o mesmo caso real do seed (spec 054, regra 2).
    receita_no_grupo_despesa = await _create_category(
        client, headers, type_="RECEITA", dre_group_id=6
    )
    despesa_no_grupo_despesa = await _create_category(
        client, headers, type_="DESPESA", dre_group_id=6
    )

    await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_no_grupo_despesa,
            cost_center_id=cost_center_id,
            account_id=account_a,
            amount="400.00",
            due_date="2026-08-10",
            competence="2026-08-01",
        ),
        headers=headers,
    )
    await client.post(
        "/api/v1/transactions",
        json={
            "kind": "DESPESA",
            "debit_account_id": account_a,
            "category_id": despesa_no_grupo_despesa,
            "cost_center_id": cost_center_id,
            "amount": "150.00",
            "due_date": "2026-08-12",
            "competence": "2026-08-01",
        },
        headers=headers,
    )

    response = await client.get(
        "/api/v1/financial-reports/dre",
        params={"from": "2026-08-01", "to": "2026-08-31"},
        headers=headers,
    )
    body = response.json()
    row = await _group_row(body["rows"], 6)
    assert row is not None
    assert row["nature"] == "DESPESA"
    assert row["receita"] == 400.0
    assert row["despesa"] == 150.0
    assert row["total"] == 250.0


async def test_transferencia_e_interno_nunca_entram(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    receita_id, _despesa_id, cost_center_id, account_a, account_b = await _fixtures(client, headers)

    await client.post(
        "/api/v1/transactions",
        json={
            "kind": "TRANSFERENCIA",
            "debit_account_id": account_a,
            "credit_account_id": account_b,
            "amount": "999.00",
            "due_date": "2026-08-10",
        },
        headers=headers,
    )
    await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            amount="777.00",
            due_date="2026-08-10",
            competence="2026-08-01",
            is_internal=True,
        ),
        headers=headers,
    )

    response = await client.get(
        "/api/v1/financial-reports/dre",
        params={"from": "2026-08-01", "to": "2026-08-31"},
        headers=headers,
    )
    body = response.json()
    assert body["rows"] == []
    assert body["total_receita"] == 0.0


async def test_filtro_por_conta_restringe_relatorio(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    receita_id, _despesa_id, cost_center_id, account_a, account_b = await _fixtures(client, headers)

    await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            amount="500.00",
            due_date="2026-08-10",
            competence="2026-08-01",
        ),
        headers=headers,
    )
    await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_b,
            amount="222.00",
            due_date="2026-08-11",
            competence="2026-08-01",
        ),
        headers=headers,
    )

    response = await client.get(
        "/api/v1/financial-reports/dre",
        params={"from": "2026-08-01", "to": "2026-08-31", "account_id": account_a},
        headers=headers,
    )
    body = response.json()
    assert body["total_receita"] == 500.0


async def test_periodo_invertido_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    response = await client.get(
        "/api/v1/financial-reports/dre",
        params={"from": "2026-08-31", "to": "2026-08-01"},
        headers=headers,
    )
    assert response.status_code == 422


async def test_export_xlsx_e_pdf_geram_arquivo_nao_vazio(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    receita_id, _despesa_id, cost_center_id, account_a, _b = await _fixtures(client, headers)
    await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            amount="100.00",
            due_date="2026-08-10",
            competence="2026-08-01",
        ),
        headers=headers,
    )

    for format_ in ("xlsx", "pdf"):
        response = await client.post(
            "/api/v1/financial-reports/export",
            json={
                "report": "dre",
                "from": "2026-08-01",
                "to": "2026-08-31",
                "format": format_,
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert len(response.content) > 0


async def test_visualizador_le_relatorio_mas_colaborador_sem_acesso_nao(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    viewer = await make_user(role=UserRole.COLABORADOR, financial_access=FinancialAccess.READ_ONLY)
    response = await client.get(
        "/api/v1/financial-reports/dre",
        params={"from": "2026-08-01", "to": "2026-08-31"},
        headers=_auth_header(viewer),
    )
    assert response.status_code == 200

    blocked = await make_user(role=UserRole.COLABORADOR, financial_access=FinancialAccess.NONE)
    response = await client.get(
        "/api/v1/financial-reports/dre",
        params={"from": "2026-08-01", "to": "2026-08-31"},
        headers=_auth_header(blocked),
    )
    assert response.status_code == 403


async def test_tenant_a_nao_ve_lancamento_de_tenant_b_no_relatorio(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor_a, headers_a = await _make_gestor_full(make_user)
    receita_id, _despesa_id, cost_center_id, account_a, _b = await _fixtures(client, headers_a)
    await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            amount="900.00",
            due_date="2026-08-10",
            competence="2026-08-01",
        ),
        headers=headers_a,
    )

    _gestor_b, headers_b = await _make_gestor_full(make_user)
    response = await client.get(
        "/api/v1/financial-reports/dre",
        params={"from": "2026-08-01", "to": "2026-08-31"},
        headers=headers_b,
    )
    body = response.json()
    assert body["rows"] == []
    assert body["total_receita"] == 0.0
