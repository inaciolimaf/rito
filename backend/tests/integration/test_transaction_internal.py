"""Financeiro: registro interno e anexos (spec 058, §8) — interno fora do caixa mas
visível na listagem/painel do processo, conversão interno↔efetivo, anexos por
lançamento (limite de 20) e exclusão em cascata."""

from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuits import (
    _create_customer,
    _create_lawsuit,
    _create_lawsuit_type,
    _create_stage,
)
from tests.integration.test_transactions import (
    _fixtures,
    _make_gestor_full,
    _receita_payload,
)

SessionFactory = async_sessionmaker[AsyncSession]


async def test_interno_nao_altera_saldo_da_conta(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    receita_id, _d, cost_center_id, account_a, _b = await _fixtures(client, headers)

    balance_before = await client.get(f"/api/v1/bank-accounts/{account_a}/balance", headers=headers)
    assert balance_before.status_code == 200

    created = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            amount="9999.00",
            is_internal=True,
        ),
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["is_internal"] is True

    balance_after = await client.get(f"/api/v1/bank-accounts/{account_a}/balance", headers=headers)
    assert balance_after.json()["balance"] == balance_before.json()["balance"]


async def test_interno_fora_do_painel_de_caixa_mas_visivel_na_listagem_do_processo(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor, headers = await _make_gestor_full(make_user)
    receita_id, _d, cost_center_id, account_a, _b = await _fixtures(client, headers)
    type_id, _group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    customer_id = await _create_customer(client, headers, "Cliente Interno")
    lawsuit = await _create_lawsuit(
        client,
        headers,
        user_id=str(gestor.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
        parties=[{"customer_id": customer_id, "pole": "ATIVO", "is_client": True}],
    )

    created = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            customer_id=customer_id,
            lawsuit_id=lawsuit["id"],
            amount="5000.00",
            payment_date="2026-08-10",
            is_internal=True,
            internal_note="Honorário a combinar",
        ),
        headers=headers,
    )
    assert created.status_code == 201, created.text

    # Regra 1: fora dos agregados de caixa do painel do processo.
    summary = await client.get(
        f"/api/v1/lawsuits/{lawsuit['id']}/financial-summary", headers=headers
    )
    assert summary.status_code == 200
    assert summary.json()["received"] == 0
    assert summary.json()["net_result"] == 0

    # Regra 2: continua visível na listagem do processo, marcado como interno.
    listed = await client.get(
        "/api/v1/transactions", headers=headers, params={"lawsuit_id": str(lawsuit["id"])}
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    item = listed.json()["items"][0]
    assert item["is_internal"] is True
    assert item["internal_note"] == "Honorário a combinar"


async def test_filtro_internal_na_listagem(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    receita_id, _d, cost_center_id, account_a, _b = await _fixtures(client, headers)

    internal = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            description="interno",
            is_internal=True,
        ),
        headers=headers,
    )
    effective = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            description="efetivo",
        ),
        headers=headers,
    )
    assert internal.status_code == 201 and effective.status_code == 201

    default = await client.get("/api/v1/transactions", headers=headers)
    assert default.json()["total"] == 2  # regra 9: padrão mostra todos

    only_internal = await client.get(
        "/api/v1/transactions", headers=headers, params={"internal": "true"}
    )
    assert [item["description"] for item in only_internal.json()["items"]] == ["INTERNO"]

    only_effective = await client.get(
        "/api/v1/transactions", headers=headers, params={"internal": "false"}
    )
    assert [item["description"] for item in only_effective.json()["items"]] == ["EFETIVO"]


async def test_converter_interno_em_efetivo(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    receita_id, _d, cost_center_id, account_a, _b = await _fixtures(client, headers)

    created = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            is_internal=True,
        ),
        headers=headers,
    )
    assert created.json()["is_internal"] is True

    updated = await client.put(
        f"/api/v1/transactions/{created.json()['id']}",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            is_internal=False,
        ),
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["is_internal"] is False


async def test_converter_pago_em_interno_retorna_409(
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
        json={"payment_date": "2026-08-10"},
        headers=headers,
    )

    attempt = await client.put(
        f"/api/v1/transactions/{transaction_id}",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            payment_date="2026-08-10",
            is_internal=True,
        ),
        headers=headers,
    )
    assert attempt.status_code == 409

    await client.post(f"/api/v1/transactions/{transaction_id}/unpay", headers=headers)
    after_unpay = await client.put(
        f"/api/v1/transactions/{transaction_id}",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            is_internal=True,
        ),
        headers=headers,
    )
    assert after_unpay.status_code == 200


async def _create_transaction(client: AsyncClient, headers: dict[str, str]) -> str:
    receita_id, _d, cost_center_id, account_a, _b = await _fixtures(client, headers)
    created = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id, cost_center_id=cost_center_id, account_id=account_a
        ),
        headers=headers,
    )
    assert created.status_code == 201, created.text
    result: str = created.json()["id"]
    return result


async def test_anexo_vinculado_e_listado(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    transaction_id = await _create_transaction(client, headers)

    upload = await client.post(
        f"/api/v1/transactions/{transaction_id}/attachments",
        files={"file": ("comprovante.pdf", b"%PDF-1.4 conteudo", "application/pdf")},
        headers=headers,
    )
    assert upload.status_code == 201, upload.text
    assert upload.json()["attached_to_type"] == "transaction"
    assert upload.json()["attached_to_id"] == transaction_id

    listed = await client.get(f"/api/v1/transactions/{transaction_id}/attachments", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["filename"] == "comprovante.pdf"


async def test_21o_anexo_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    transaction_id = await _create_transaction(client, headers)

    for i in range(20):
        response = await client.post(
            f"/api/v1/transactions/{transaction_id}/attachments",
            files={"file": (f"doc{i}.pdf", b"%PDF-1.4 x", "application/pdf")},
            headers=headers,
        )
        assert response.status_code == 201, response.text

    twenty_first = await client.post(
        f"/api/v1/transactions/{transaction_id}/attachments",
        files={"file": ("doc21.pdf", b"%PDF-1.4 x", "application/pdf")},
        headers=headers,
    )
    assert twenty_first.status_code == 422


async def test_excluir_lancamento_remove_anexos(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: SessionFactory,
) -> None:
    gestor, headers = await _make_gestor_full(make_user)
    transaction_id = await _create_transaction(client, headers)

    upload = await client.post(
        f"/api/v1/transactions/{transaction_id}/attachments",
        files={"file": ("comprovante.pdf", b"%PDF-1.4 conteudo", "application/pdf")},
        headers=headers,
    )
    assert upload.status_code == 201

    delete = await client.delete(f"/api/v1/transactions/{transaction_id}", headers=headers)
    assert delete.status_code == 204

    async with app_session_factory() as session:
        await set_tenant_context(session, gestor.tenant_id)
        count = (
            await session.execute(
                text(
                    "SELECT count(*) FROM attachments WHERE attached_to_type = 'transaction' "
                    "AND attached_to_id = CAST(:id AS uuid)"
                ),
                {"id": transaction_id},
            )
        ).scalar_one()
    assert count == 0
