"""Modelos: biblioteca (spec 064, §8) — CRUD, tipos fixos, lixeira reversível,
duplicação, busca/filtro combinados e isolamento por tenant."""

import uuid
from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.core.tokens import create_access_token
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser


def _auth_header(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)
    return {"Authorization": f"Bearer {token}"}


async def _create_template(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    name: str | None = None,
    type_: str = "CONTRATO",
) -> dict[str, object]:
    response = await client.post(
        "/api/v1/templates",
        json={"name": name or f"Modelo {uuid.uuid4().hex[:8]}", "type": type_, "content": "corpo"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    result: dict[str, object] = response.json()
    return result


async def test_crud_completo(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.COLABORADOR)
    headers = _auth_header(user)

    created = await _create_template(client, headers, name="Contrato de honorários")
    template_id = created["id"]
    assert created["type"] == "CONTRATO"
    assert created["deleted_at"] is None

    get_response = await client.get(f"/api/v1/templates/{template_id}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Contrato de honorários"

    update_response = await client.put(
        f"/api/v1/templates/{template_id}",
        json={"name": "Contrato revisado", "type": "PETICAO", "content": "novo corpo"},
        headers=headers,
    )
    assert update_response.status_code == 200
    body = update_response.json()
    assert body["name"] == "Contrato revisado"
    assert body["type"] == "PETICAO"


async def test_tipo_invalido_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.COLABORADOR)
    headers = _auth_header(user)
    response = await client.post(
        "/api/v1/templates",
        json={"name": "X", "type": "INVALIDO", "content": ""},
        headers=headers,
    )
    assert response.status_code == 422


async def test_excluir_move_para_lixeira_e_some_da_listagem_normal(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.COLABORADOR)
    headers = _auth_header(user)
    created = await _create_template(client, headers, name="Vai pra lixeira")
    template_id = created["id"]

    delete_response = await client.delete(f"/api/v1/templates/{template_id}", headers=headers)
    assert delete_response.status_code == 204

    listing = await client.get("/api/v1/templates", headers=headers)
    names = [item["name"] for item in listing.json()["items"]]
    assert "Vai pra lixeira" not in names


async def test_lixeira_lista_so_os_excluidos(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.COLABORADOR)
    headers = _auth_header(user)
    kept = await _create_template(client, headers, name="Fica")
    trashed = await _create_template(client, headers, name="Some")
    await client.delete(f"/api/v1/templates/{trashed['id']}", headers=headers)

    trash_listing = await client.get("/api/v1/templates", params={"view": "trash"}, headers=headers)
    names = [item["name"] for item in trash_listing.json()["items"]]
    assert names == ["Some"]
    assert kept["id"] not in [item["id"] for item in trash_listing.json()["items"]]


async def test_restaurar_devolve_a_listagem_normal(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.COLABORADOR)
    headers = _auth_header(user)
    created = await _create_template(client, headers, name="Volta")
    template_id = created["id"]
    await client.delete(f"/api/v1/templates/{template_id}", headers=headers)

    restore_response = await client.post(
        f"/api/v1/templates/{template_id}/restore", headers=headers
    )
    assert restore_response.status_code == 200
    assert restore_response.json()["deleted_at"] is None

    listing = await client.get("/api/v1/templates", headers=headers)
    names = [item["name"] for item in listing.json()["items"]]
    assert "Volta" in names

    trash_listing = await client.get("/api/v1/templates", params={"view": "trash"}, headers=headers)
    assert "Volta" not in [item["name"] for item in trash_listing.json()["items"]]


async def test_duplicar_copia_nome_tipo_conteudo_com_sufixo(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.COLABORADOR)
    headers = _auth_header(user)
    original = await _create_template(client, headers, name="Petição inicial", type_="PETICAO")

    duplicate_response = await client.post(
        f"/api/v1/templates/{original['id']}/duplicate", headers=headers
    )
    assert duplicate_response.status_code == 201
    copy = duplicate_response.json()
    assert copy["name"] == "Petição inicial (cópia)"
    assert copy["type"] == "PETICAO"
    assert copy["content"] == original["content"]
    assert copy["id"] != original["id"]


async def test_duplicar_modelo_da_lixeira_gera_copia_ativa(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.COLABORADOR)
    headers = _auth_header(user)
    original = await _create_template(client, headers, name="Descartado")
    await client.delete(f"/api/v1/templates/{original['id']}", headers=headers)

    duplicate_response = await client.post(
        f"/api/v1/templates/{original['id']}/duplicate", headers=headers
    )
    assert duplicate_response.status_code == 201
    assert duplicate_response.json()["deleted_at"] is None


async def test_busca_por_nome_e_case_insensitive(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.COLABORADOR)
    headers = _auth_header(user)
    await _create_template(client, headers, name="Procuração Especial")
    await _create_template(client, headers, name="Outro modelo")

    response = await client.get("/api/v1/templates", params={"q": "procuração"}, headers=headers)
    names = [item["name"] for item in response.json()["items"]]
    assert names == ["Procuração Especial"]


async def test_filtro_por_tipo_combina_com_busca(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.COLABORADOR)
    headers = _auth_header(user)
    await _create_template(client, headers, name="Recurso especial", type_="RECURSO")
    await _create_template(client, headers, name="Recurso comum", type_="DOCUMENTO")

    response = await client.get(
        "/api/v1/templates", params={"view": "RECURSO", "q": "especial"}, headers=headers
    )
    names = [item["name"] for item in response.json()["items"]]
    assert names == ["Recurso especial"]


async def test_tenant_a_nao_ve_restaura_ou_duplica_modelo_de_tenant_b(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user_a = await make_user(role=UserRole.COLABORADOR)
    headers_a = _auth_header(user_a)
    created = await _create_template(client, headers_a, name="Só do tenant A")
    template_id = created["id"]

    user_b = await make_user(role=UserRole.COLABORADOR)
    headers_b = _auth_header(user_b)

    assert (
        await client.get(f"/api/v1/templates/{template_id}", headers=headers_b)
    ).status_code == 404
    assert (
        await client.post(f"/api/v1/templates/{template_id}/restore", headers=headers_b)
    ).status_code == 404
    assert (
        await client.post(f"/api/v1/templates/{template_id}/duplicate", headers=headers_b)
    ).status_code == 404

    listing = await client.get("/api/v1/templates", headers=headers_b)
    assert listing.json()["items"] == []
