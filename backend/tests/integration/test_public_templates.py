"""Biblioteca pública de modelos (spec 068, §8) — catálogo global, filtro por tipo,
cópia editável do tenant e isolamento entre tenants que copiam o mesmo original."""

import uuid
from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser, auth_header


async def _list_public_templates(
    client: AsyncClient, headers: dict[str, str], **params: str
) -> list[dict[str, object]]:
    response = await client.get("/api/v1/public-templates", params=params, headers=headers)
    assert response.status_code == 200, response.text
    result: list[dict[str, object]] = response.json()
    return result


async def test_lista_modelos_publicos_e_filtra_por_tipo(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.COLABORADOR)
    headers = auth_header(user)

    all_items = await _list_public_templates(client, headers)
    assert len(all_items) == 6
    assert {item["type"] for item in all_items} == {"CONTRATO", "PETICAO", "RECURSO", "DOCUMENTO"}

    contracts = await _list_public_templates(client, headers, type="CONTRATO")
    assert len(contracts) == 2
    assert all(item["type"] == "CONTRATO" for item in contracts)


async def test_copiar_cria_modelo_editavel_do_tenant_sem_sufixo_no_nome(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.COLABORADOR)
    headers = auth_header(user)
    original = (await _list_public_templates(client, headers, type="CONTRATO"))[0]

    copy_response = await client.post(
        f"/api/v1/public-templates/{original['id']}/copy", headers=headers
    )
    assert copy_response.status_code == 201, copy_response.text
    copy = copy_response.json()
    assert copy["name"] == original["name"]
    assert copy["content"] == original["content"]
    assert copy["deleted_at"] is None

    # É um Template comum do tenant dali em diante (spec 064): aparece na listagem
    # normal e pode ser editado/excluído como qualquer outro.
    listing = await client.get("/api/v1/templates", headers=headers)
    names = [item["name"] for item in listing.json()["items"]]
    assert original["name"] in names

    update_response = await client.put(
        f"/api/v1/templates/{copy['id']}",
        json={"name": "Renomeado após copiar", "type": copy["type"], "content": copy["content"]},
        headers=headers,
    )
    assert update_response.status_code == 200, update_response.text


async def test_copia_de_tenants_diferentes_nao_interfere_entre_si(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user_a = await make_user(role=UserRole.COLABORADOR)
    headers_a = auth_header(user_a)
    original = (await _list_public_templates(client, headers_a, type="PETICAO"))[0]

    copy_a = await client.post(f"/api/v1/public-templates/{original['id']}/copy", headers=headers_a)
    assert copy_a.status_code == 201

    user_b = await make_user(role=UserRole.COLABORADOR)
    headers_b = auth_header(user_b)
    copy_b = await client.post(f"/api/v1/public-templates/{original['id']}/copy", headers=headers_b)
    assert copy_b.status_code == 201
    assert copy_b.json()["id"] != copy_a.json()["id"]

    # tenant B não vê a cópia de A (RLS, mesmo padrão de qualquer outra tabela).
    listing_b = await client.get("/api/v1/templates", headers=headers_b)
    ids_b = {item["id"] for item in listing_b.json()["items"]}
    assert copy_a.json()["id"] not in ids_b
    assert copy_b.json()["id"] in ids_b


async def test_copiar_modelo_publico_inexistente_retorna_404(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.COLABORADOR)
    headers = auth_header(user)

    response = await client.post(f"/api/v1/public-templates/{uuid.uuid4()}/copy", headers=headers)
    assert response.status_code == 404
