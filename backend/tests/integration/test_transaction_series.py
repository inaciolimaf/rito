"""Financeiro: recorrência e parcelamento (spec 057, §8) — parcelamento gerado por
inteiro na criação (com sufixo e vencimento mensal), recorrência gerada aos poucos por
um worker que nunca cria tudo de uma vez, edição/exclusão por escopo e o limite de
100 parcelas."""

import uuid
from collections.abc import Awaitable, Callable
from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.financial.service import TransactionSeriesService
from tests.integration.conftest import SeededUser
from tests.integration.test_transactions import (
    _fixtures,
    _make_gestor_full,
    _receita_payload,
)

SessionFactory = async_sessionmaker[AsyncSession]


async def test_parcelamento_gera_12_parcelas_com_vencimentos_mensais(
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
            amount="1200.00",
            due_date="2026-01-15",
            installment={"count": 12},
        ),
        headers=headers,
    )
    assert created.status_code == 201, created.text
    first = created.json()
    assert first["due_date"] == "2026-01-15"
    assert first["installment_number"] == 1
    series_id = first["series_id"]
    assert series_id is not None

    preview = await client.get(
        f"/api/v1/transactions/{first['id']}/series-preview", headers=headers
    )
    assert preview.status_code == 200, preview.text
    items = preview.json()["items"]
    assert len(items) == 12
    assert [item["installment_number"] for item in items] == list(range(1, 13))
    assert [item["due_date"] for item in items] == [
        f"2026-{month:02d}-15" for month in range(1, 13)
    ]
    assert sum(item["amount"] for item in items) == 1200.00


async def test_parcelamento_sufixo_n_de_n_na_descricao(
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
            description="Honorários contratuais",
            due_date="2026-01-15",
            installment={"count": 3},
        ),
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["description"] == "HONORÁRIOS CONTRATUAIS (1/3)"

    listed = await client.get("/api/v1/transactions", headers=headers, params={"q": "2/3"})
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["description"] == "HONORÁRIOS CONTRATUAIS (2/3)"


async def test_parcela_31_em_fevereiro_usa_ultimo_dia_do_mes(
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
            due_date="2026-01-31",
            installment={"count": 3},
        ),
        headers=headers,
    )
    assert created.status_code == 201, created.text

    preview = await client.get(
        f"/api/v1/transactions/{created.json()['id']}/series-preview", headers=headers
    )
    dates = [item["due_date"] for item in preview.json()["items"]]
    assert dates == ["2026-01-31", "2026-02-28", "2026-03-31"]


async def test_101_parcelas_retorna_422(
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
            installment={"count": 101},
        ),
        headers=headers,
    )
    assert response.status_code == 422


async def test_installment_e_recurrence_juntos_retorna_422(
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
            installment={"count": 3},
            recurrence={"period": "MENSAL"},
        ),
        headers=headers,
    )
    assert response.status_code == 422


async def test_recorrencia_cria_so_a_primeira_ocorrencia(
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
            due_date="2026-01-15",
            recurrence={"period": "MENSAL"},
        ),
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["installment_number"] is None
    series_id = created.json()["series_id"]
    assert series_id is not None

    preview = await client.get(
        f"/api/v1/transactions/{created.json()['id']}/series-preview", headers=headers
    )
    assert len(preview.json()["items"]) == 1

    series = await client.get(f"/api/v1/transaction-series/{series_id}", headers=headers)
    assert series.status_code == 200, series.text
    assert series.json()["generated_until"] == "2026-01-15"
    assert series.json()["is_active"] is True


async def test_worker_gera_so_3_meses_a_frente_e_avanca_generated_until(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: SessionFactory,
) -> None:
    gestor, headers = await _make_gestor_full(make_user)
    receita_id, _d, cost_center_id, account_a, _b = await _fixtures(client, headers)

    created = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            due_date="2026-01-15",
            recurrence={"period": "MENSAL"},
        ),
        headers=headers,
    )
    series_id = uuid.UUID(created.json()["series_id"])

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, gestor.tenant_id)
        service = TransactionSeriesService(session=session, tenant_id=gestor.tenant_id)
        series = await service.get(series_id)
        assert series is not None
        generated = await service.generate_recurrence(series, date(2026, 1, 20))

    assert generated == 3

    preview = await client.get(
        f"/api/v1/transactions/{created.json()['id']}/series-preview", headers=headers
    )
    dates = sorted(item["due_date"] for item in preview.json()["items"])
    assert dates == ["2026-01-15", "2026-02-15", "2026-03-15", "2026-04-15"]

    series_after = await client.get(f"/api/v1/transaction-series/{series_id}", headers=headers)
    assert series_after.json()["generated_until"] == "2026-04-15"


async def test_scope_future_nao_toca_parcela_paga(
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
            due_date="2026-01-15",
            installment={"count": 3},
        ),
        headers=headers,
    )
    series_id = created.json()["series_id"]

    preview = await client.get(
        f"/api/v1/transactions/{created.json()['id']}/series-preview", headers=headers
    )
    first_id = preview.json()["items"][0]["id"]
    await client.post(
        f"/api/v1/transactions/{first_id}/pay",
        json={"payment_date": "2026-01-10"},
        headers=headers,
    )

    update = await client.put(
        f"/api/v1/transaction-series/{series_id}",
        params={"scope": "all"},
        json={"description": "renegociado"},
        headers=headers,
    )
    assert update.status_code == 200, update.text
    updated_ids = {item["id"] for item in update.json()["items"]}
    assert first_id not in updated_ids
    assert len(update.json()["items"]) == 2
    for item in update.json()["items"]:
        assert item["description"] == "RENEGOCIADO"

    # sem GET /transactions/{id} dedicado — confere via preview que a paga não mudou
    preview_after = await client.get(
        f"/api/v1/transactions/{created.json()['id']}/series-preview", headers=headers
    )
    first_after = next(item for item in preview_after.json()["items"] if item["id"] == first_id)
    assert first_after["payment_date"] == "2026-01-10"


async def test_excluir_serie_com_paga_em_scope_all_retorna_409(
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
            due_date="2026-01-15",
            installment={"count": 3},
        ),
        headers=headers,
    )
    series_id = created.json()["series_id"]
    await client.post(
        f"/api/v1/transactions/{created.json()['id']}/pay",
        json={"payment_date": "2026-01-10"},
        headers=headers,
    )

    delete_all = await client.delete(
        f"/api/v1/transaction-series/{series_id}", params={"scope": "all"}, headers=headers
    )
    assert delete_all.status_code == 409

    delete_future = await client.delete(
        f"/api/v1/transaction-series/{series_id}", params={"scope": "future"}, headers=headers
    )
    assert delete_future.status_code == 204

    preview = await client.get(
        f"/api/v1/transactions/{created.json()['id']}/series-preview", headers=headers
    )
    assert len(preview.json()["items"]) == 1
    assert preview.json()["items"][0]["payment_date"] == "2026-01-10"


async def test_encerrar_recorrencia_preserva_o_ja_gerado(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: SessionFactory,
) -> None:
    gestor, headers = await _make_gestor_full(make_user)
    receita_id, _d, cost_center_id, account_a, _b = await _fixtures(client, headers)

    created = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            due_date="2026-01-15",
            recurrence={"period": "MENSAL"},
        ),
        headers=headers,
    )
    series_id = uuid.UUID(created.json()["series_id"])
    first_id = created.json()["id"]

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, gestor.tenant_id)
        service = TransactionSeriesService(session=session, tenant_id=gestor.tenant_id)
        series = await service.get(series_id)
        assert series is not None
        await service.generate_recurrence(series, date(2026, 1, 20))

    # "o já criado" que a regra 9 preserva é o que já virou fato financeiro (pago) —
    # as ocorrências em aberto são removidas junto com o encerramento (regra 8).
    await client.post(
        f"/api/v1/transactions/{first_id}/pay", json={"payment_date": "2026-01-15"}, headers=headers
    )

    end_series = await client.delete(
        f"/api/v1/transaction-series/{series_id}", params={"scope": "future"}, headers=headers
    )
    assert end_series.status_code == 204

    series_after = await client.get(f"/api/v1/transaction-series/{series_id}", headers=headers)
    assert series_after.json()["is_active"] is False

    preview = await client.get(f"/api/v1/transactions/{first_id}/series-preview", headers=headers)
    items = preview.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == first_id
    assert items[0]["payment_date"] == "2026-01-15"


async def test_tenant_a_nao_ve_serie_de_tenant_b(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor_a, headers_a = await _make_gestor_full(make_user)
    receita_id, _d, cost_center_id, account_a, _b = await _fixtures(client, headers_a)
    created = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            due_date="2026-01-15",
            installment={"count": 3},
        ),
        headers=headers_a,
    )
    series_id = created.json()["series_id"]

    _gestor_b, headers_b = await _make_gestor_full(make_user)
    response = await client.get(f"/api/v1/transaction-series/{series_id}", headers=headers_b)
    assert response.status_code == 404
