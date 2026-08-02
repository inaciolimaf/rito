import uuid
from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuits import (
    _auth_header,
    _create_lawsuit,
    _create_lawsuit_type,
    _create_stage,
)


async def _setup(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> tuple[SeededUser, dict[str, str], str, str]:
    """Gestor + tipo + etapa prontos para criar processo."""
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    type_id, _group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    return gestor, headers, type_id, stage_id


async def test_valores_monetarios_sem_perda_de_precisao(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor, headers, type_id, stage_id = await _setup(client, make_user)

    created = await _create_lawsuit(
        client,
        headers,
        user_id=str(gestor.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
        case_value=123456.78,
        fees_value=999999999999.99,
        fees_percentage=17.55,
        contingency="POSSIVEL",
        closure_date="2026-01-10",
    )

    assert created["case_value"] == 123456.78
    assert created["fees_value"] == 999999999999.99
    assert created["fees_percentage"] == 17.55
    assert created["contingency"] == "POSSIVEL"
    assert created["closure_date"] == "2026-01-10"

    # Ida e volta: o GET devolve exatamente o que foi salvo (regra 1).
    get_response = await client.get(f"/api/v1/lawsuits/{created['id']}", headers=headers)
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["case_value"] == 123456.78
    assert body["fees_value"] == 999999999999.99
    assert body["fees_percentage"] == 17.55


async def test_percentual_acima_de_100_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor, headers, type_id, stage_id = await _setup(client, make_user)
    customer_id = str(uuid.uuid4())
    response = await client.post(
        "/api/v1/lawsuits",
        json={
            "user_id": str(gestor.user_id),
            "lawsuit_type_id": type_id,
            "stage_id": stage_id,
            "parties": [{"customer_id": customer_id, "pole": "ATIVO", "is_client": True}],
            "fees_percentage": 100.01,
        },
        headers=headers,
    )
    assert response.status_code == 422


async def test_transito_anterior_ao_fechamento_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor, headers, type_id, stage_id = await _setup(client, make_user)
    response = await client.post(
        "/api/v1/lawsuits",
        json={
            "user_id": str(gestor.user_id),
            "lawsuit_type_id": type_id,
            "stage_id": stage_id,
            "parties": [{"customer_id": str(uuid.uuid4()), "pole": "ATIVO", "is_client": True}],
            "closure_date": "2026-02-01",
            "transit_date": "2026-01-01",
        },
        headers=headers,
    )
    assert response.status_code == 422


async def test_arquivamento_anterior_ao_transito_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor, headers, type_id, stage_id = await _setup(client, make_user)
    created = await _create_lawsuit(
        client,
        headers,
        user_id=str(gestor.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
        closure_date="2026-01-01",
        transit_date="2026-03-01",
    )
    # Via PUT (a constraint ck_cycle protege também o update).
    response = await client.put(
        f"/api/v1/lawsuits/{created['id']}",
        json={
            "user_id": str(gestor.user_id),
            "lawsuit_type_id": type_id,
            "stage_id": stage_id,
            "closure_date": "2026-01-01",
            "transit_date": "2026-03-01",
            "archived_date": "2026-02-01",
        },
        headers=headers,
    )
    assert response.status_code == 422


async def test_outcome_sem_fechamento_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor, headers, type_id, stage_id = await _setup(client, make_user)
    response = await client.post(
        "/api/v1/lawsuits",
        json={
            "user_id": str(gestor.user_id),
            "lawsuit_type_id": type_id,
            "stage_id": stage_id,
            "parties": [{"customer_id": str(uuid.uuid4()), "pole": "ATIVO", "is_client": True}],
            "outcome": "GANHO",
        },
        headers=headers,
    )
    assert response.status_code == 422


async def test_outcome_com_fechamento_e_aceito(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor, headers, type_id, stage_id = await _setup(client, make_user)
    created = await _create_lawsuit(
        client,
        headers,
        user_id=str(gestor.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
        closure_date="2026-01-15",
        transit_date="2026-04-20",
        archived_date="2026-05-01",
        outcome="ACORDO",
    )
    assert created["outcome"] == "ACORDO"
    assert created["archived_date"] == "2026-05-01"
    # Regra 5: archived_date é fato processual — NÃO arquiva o registro.
    assert created["is_archived"] is False


async def test_valor_negativo_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor, headers, type_id, stage_id = await _setup(client, make_user)
    for field in ("case_value", "fees_value", "fees_percentage"):
        response = await client.post(
            "/api/v1/lawsuits",
            json={
                "user_id": str(gestor.user_id),
                "lawsuit_type_id": type_id,
                "stage_id": stage_id,
                "parties": [{"customer_id": str(uuid.uuid4()), "pole": "ATIVO", "is_client": True}],
                field: -1,
            },
            headers=headers,
        )
        assert response.status_code == 422, field


async def test_financial_summary_zerado_ate_a_spec_056(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor, headers, type_id, stage_id = await _setup(client, make_user)
    created = await _create_lawsuit(
        client,
        headers,
        user_id=str(gestor.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
        case_value=50000.00,
        fees_value=10000.00,
    )

    response = await client.get(
        f"/api/v1/lawsuits/{created['id']}/financial-summary", headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["case_value"] == 50000.00
    assert body["fees_value"] == 10000.00
    assert body["received"] == 0
    assert body["to_receive"] == 0
    assert body["expenses"] == 0
    assert body["net_result"] == 0


async def test_financial_summary_processo_inexistente_retorna_404(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    response = await client.get(
        f"/api/v1/lawsuits/{uuid.uuid4()}/financial-summary", headers=_auth_header(gestor)
    )
    assert response.status_code == 404
