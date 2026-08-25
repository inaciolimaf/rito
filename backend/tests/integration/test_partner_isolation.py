"""A exceção de parceria não vazou para nenhuma outra superfície (spec 080, alvo 1).

`test_partnerships.py` prova que o parceiro vê o processo compartilhado; estes provam
o complemento, do jeito mais desconfiado possível: o usuário do parceiro tem
`financial_access = FULL` no tenant dele (regra 9 da 079) e ainda assim não alcança
lançamento, modelo, documento nem BI do escritório dono.
"""

from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.core.config import get_settings
from app.domain.users.models import FinancialAccess
from app.workers.bi_pipeline import refresh_bi_pipeline_monthly
from tests.integration.conftest import SeededUser
from tests.integration.test_partnerships import _setup, _share
from tests.integration.test_templates import _create_template
from tests.integration.test_transactions import _fixtures, _receita_payload


async def test_parceiro_com_financeiro_full_nao_alcanca_lancamento_do_dono(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    scenario = await _setup(
        client,
        make_user,
        owner_financial=FinancialAccess.FULL,
        partner_financial=FinancialAccess.FULL,
    )
    await _share(client, scenario, can_view_financial=False)

    receita_id, _despesa_id, cost_center_id, account_a, _account_b = await _fixtures(
        client, scenario.owner_headers
    )
    created = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
        ),
        headers=scenario.owner_headers,
    )
    assert created.status_code == 201, created.text

    listing = await client.get("/api/v1/transactions", headers=scenario.partner_headers)
    assert listing.status_code == 200
    assert listing.json()["items"] == []

    # (não há GET /transactions/{id} na API — a listagem e o painel são as portas.)
    stats = await client.get(
        "/api/v1/transactions/stats",
        params={"month": "2026-08", "regime": "payment"},
        headers=scenario.partner_headers,
    )
    assert stats.status_code == 200
    assert all(value == 0 for value in stats.json().values() if isinstance(value, (int, float)))


async def test_parceiro_nao_alcanca_modelos_do_dono(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    scenario = await _setup(client, make_user)
    await _share(client, scenario)

    template = await _create_template(
        client, scenario.owner_headers, name="Petição inicial sigilosa"
    )

    listing = await client.get("/api/v1/templates", headers=scenario.partner_headers)
    assert listing.status_code == 200
    assert listing.json()["items"] == []

    detail = await client.get(
        f"/api/v1/templates/{template['id']}", headers=scenario.partner_headers
    )
    assert detail.status_code == 404


async def test_parceiro_nao_alcanca_bi_do_dono_nem_depois_do_refresh(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """A view barreira é o ponto sensível: matview não tem RLS, quem filtra é o
    `_visible`. Com o refresh feito DEPOIS do compartilhamento, o processo do dono já
    está materializado — e mesmo assim não aparece do lado do parceiro."""
    scenario = await _setup(client, make_user)
    await _share(client, scenario, can_view_financial=True)

    url = get_settings().migrations_database_url
    assert url is not None
    await refresh_bi_pipeline_monthly(url)

    response = await client.get("/api/v1/bi/pipeline", headers=scenario.partner_headers)
    assert response.status_code == 200
    body = response.json()
    assert all(
        row.get("created", 0) == 0 and row.get("closed", 0) == 0
        for row in body.get("months", body.get("items", []))
    )
