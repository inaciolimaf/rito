from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuits import (
    _auth_header,
    _create_customer,
    _create_lawsuit_type,
    _create_stage,
)


async def test_validate_number_valido_com_tribunal_inferido(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    response = await client.post(
        "/api/v1/lawsuits/validate-number",
        json={"process_number": "0700700-18.2025.8.26.0100"},
        headers=_auth_header(gestor),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["formatted"] == "0700700-18.2025.8.26.0100"
    assert body["parsed"]["year"] == 2025
    assert body["parsed"]["segment"] == 8
    assert body["parsed"]["segment_name"] == "Justiça Estadual"
    assert body["inferred_court"]["code"] == "TJSP"
    assert body["error"] is None


async def test_validate_number_invalido_retorna_erro_especifico(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    response = await client.post(
        "/api/v1/lawsuits/validate-number",
        json={"process_number": "0000123-77.2025.1.00.0001"},
        headers=_auth_header(gestor),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert "Dígito verificador não confere" in body["error"]
    assert body["parsed"] is None


async def test_criar_processo_com_numero_invalido_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    type_id, _group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    customer_id = await _create_customer(client, headers, "Cliente Número Inválido")

    response = await client.post(
        "/api/v1/lawsuits",
        json={
            "user_id": str(gestor.user_id),
            "lawsuit_type_id": type_id,
            "stage_id": stage_id,
            "parties": [{"customer_id": customer_id, "pole": "ATIVO", "is_client": True}],
            "process_number": "0001234-56.2026.8.26.0100",  # DV errado (correto: 34)
        },
        headers=headers,
    )
    assert response.status_code == 422
    assert "Dígito verificador" in response.json()["detail"]


async def test_criar_processo_sem_numero_e_aceito(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    type_id, _group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    customer_id = await _create_customer(client, headers, "Cliente Sem Número")

    response = await client.post(
        "/api/v1/lawsuits",
        json={
            "user_id": str(gestor.user_id),
            "lawsuit_type_id": type_id,
            "stage_id": stage_id,
            "parties": [{"customer_id": customer_id, "pole": "ATIVO", "is_client": True}],
        },
        headers=headers,
    )
    # Regra 8: número é opcional — prospecção e administrativo não têm.
    assert response.status_code == 201
    assert response.json()["process_number"] is None
