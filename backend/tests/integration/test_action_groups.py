import uuid
from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.core.tokens import create_access_token
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser


def _auth_header(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)
    return {"Authorization": f"Bearer {token}"}


async def _create_group(client: AsyncClient, headers: dict[str, str], name: str) -> str:
    response = await client.post("/api/v1/action-groups", json={"name": name}, headers=headers)
    assert response.status_code == 201
    result: str = response.json()["id"]
    return result


async def _create_type(
    client: AsyncClient, headers: dict[str, str], name: str, group_id: str
) -> str:
    response = await client.post(
        "/api/v1/lawsuit-types",
        json={"name": name, "action_group_id": group_id},
        headers=headers,
    )
    assert response.status_code == 201
    result: str = response.json()["id"]
    return result


async def test_crud_dos_dois(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)

    group_id = await _create_group(client, headers, "Cível")
    type_id = await _create_type(client, headers, "Reintegração de Posse", group_id)

    list_groups = await client.get("/api/v1/action-groups", headers=headers)
    assert list_groups.status_code == 200
    assert any(item["id"] == group_id for item in list_groups.json()["items"])

    list_types = await client.get("/api/v1/lawsuit-types", headers=headers)
    assert list_types.status_code == 200
    type_item = next(item for item in list_types.json()["items"] if item["id"] == type_id)
    assert type_item["action_group_name"] == "Cível"

    update_group = await client.put(
        f"/api/v1/action-groups/{group_id}",
        json={"name": "Cível Renomeado", "is_active": True},
        headers=headers,
    )
    assert update_group.status_code == 200
    assert update_group.json()["name"] == "Cível Renomeado"
    assert update_group.json()["lawsuit_types_count"] == 1

    update_type = await client.put(
        f"/api/v1/lawsuit-types/{type_id}",
        json={"name": "Reintegração Renomeada", "action_group_id": group_id, "is_active": True},
        headers=headers,
    )
    assert update_type.status_code == 200
    assert update_type.json()["name"] == "Reintegração Renomeada"

    delete_type = await client.delete(f"/api/v1/lawsuit-types/{type_id}", headers=headers)
    assert delete_type.status_code == 204

    delete_group = await client.delete(f"/api/v1/action-groups/{group_id}", headers=headers)
    assert delete_group.status_code == 204


async def test_nome_duplicado_ignorando_acento_retorna_409(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)

    await _create_group(client, headers, "Cível")
    response = await client.post("/api/v1/action-groups", json={"name": "CIVEL"}, headers=headers)

    assert response.status_code == 409


async def test_excluir_grupo_com_tipo_vinculado_sem_transferir_retorna_409(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)

    group_id = await _create_group(client, headers, "Penal")
    await _create_type(client, headers, "Estelionato", group_id)

    response = await client.delete(f"/api/v1/action-groups/{group_id}", headers=headers)

    assert response.status_code == 409


async def test_transferencia_migra_e_e_transacional(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)

    origem_id = await _create_group(client, headers, "Trabalhista")
    destino_id = await _create_group(client, headers, "Financeiro/RH")
    await _create_type(client, headers, "Reclamatória", origem_id)
    await _create_type(client, headers, "Admissão", origem_id)

    transfer_response = await client.post(
        "/api/v1/lawsuit-types/transfer",
        json={"from_id": origem_id, "to_id": destino_id},
        headers=headers,
    )
    assert transfer_response.status_code == 200
    assert transfer_response.json()["transferred_count"] == 2

    # Origem esvaziada: agora pode ser excluída sem 409.
    delete_origem = await client.delete(f"/api/v1/action-groups/{origem_id}", headers=headers)
    assert delete_origem.status_code == 204

    list_types = await client.get(
        "/api/v1/lawsuit-types", params={"group_id": destino_id}, headers=headers
    )
    assert len(list_types.json()["items"]) == 2


async def test_transferencia_com_ids_iguais_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    group_id = await _create_group(client, headers, "Administrativo")

    response = await client.post(
        "/api/v1/lawsuit-types/transfer",
        json={"from_id": group_id, "to_id": group_id},
        headers=headers,
    )

    assert response.status_code == 422


async def test_transferencia_com_grupo_inexistente_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    group_id = await _create_group(client, headers, "Previdenciário")

    response = await client.post(
        "/api/v1/lawsuit-types/transfer",
        json={"from_id": group_id, "to_id": str(uuid.uuid4())},
        headers=headers,
    )

    assert response.status_code == 422


async def test_tipos_filtrados_por_grupo(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)

    grupo_a = await _create_group(client, headers, "Grupo A")
    grupo_b = await _create_group(client, headers, "Grupo B")
    await _create_type(client, headers, "Tipo A1", grupo_a)
    await _create_type(client, headers, "Tipo B1", grupo_b)

    response = await client.get(
        "/api/v1/lawsuit-types", params={"group_id": grupo_a}, headers=headers
    )

    assert response.status_code == 200
    names = {item["name"] for item in response.json()["items"]}
    assert names == {"Tipo A1"}


async def test_colaborador_recebe_403_ao_escrever(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    colaborador = await make_user(role=UserRole.COLABORADOR)
    headers = _auth_header(colaborador)

    list_response = await client.get("/api/v1/action-groups", headers=headers)
    assert list_response.status_code == 200

    create_response = await client.post(
        "/api/v1/action-groups", json={"name": "Não Autorizado"}, headers=headers
    )
    assert create_response.status_code == 403


async def test_tenant_a_nao_ve_grupo_de_tenant_b(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor_a = await make_user(role=UserRole.GESTOR)
    gestor_b = await make_user(role=UserRole.GESTOR)

    group_id = await _create_group(client, _auth_header(gestor_a), "Isolado")

    response = await client.get("/api/v1/action-groups", headers=_auth_header(gestor_b))

    ids = {item["id"] for item in response.json()["items"]}
    assert group_id not in ids


async def test_put_grupo_inexistente_retorna_404(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)

    response = await client.put(
        f"/api/v1/action-groups/{uuid.uuid4()}",
        json={"name": "Não Existe", "is_active": True},
        headers=_auth_header(gestor),
    )

    assert response.status_code == 404


async def test_renomear_grupo_para_nome_existente_retorna_409(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)

    await _create_group(client, headers, "Grupo Um")
    grupo_dois = await _create_group(client, headers, "Grupo Dois")

    response = await client.put(
        f"/api/v1/action-groups/{grupo_dois}",
        json={"name": "Grupo Um", "is_active": True},
        headers=headers,
    )

    assert response.status_code == 409


async def test_delete_grupo_inexistente_retorna_404(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)

    response = await client.delete(
        f"/api/v1/action-groups/{uuid.uuid4()}", headers=_auth_header(gestor)
    )

    assert response.status_code == 404


async def test_criar_tipo_com_nome_duplicado_retorna_409(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    group_id = await _create_group(client, headers, "Grupo X")
    await _create_type(client, headers, "Tipo Repetido", group_id)

    response = await client.post(
        "/api/v1/lawsuit-types",
        json={"name": "Tipo Repetido", "action_group_id": group_id},
        headers=headers,
    )

    assert response.status_code == 409


async def test_criar_tipo_com_grupo_inexistente_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)

    response = await client.post(
        "/api/v1/lawsuit-types",
        json={"name": "Órfão", "action_group_id": str(uuid.uuid4())},
        headers=_auth_header(gestor),
    )

    assert response.status_code == 422


async def test_put_tipo_inexistente_retorna_404(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    group_id = await _create_group(client, headers, "Grupo Y")

    response = await client.put(
        f"/api/v1/lawsuit-types/{uuid.uuid4()}",
        json={"name": "Não Existe", "action_group_id": group_id, "is_active": True},
        headers=headers,
    )

    assert response.status_code == 404


async def test_renomear_tipo_para_nome_existente_retorna_409(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    group_id = await _create_group(client, headers, "Grupo Z")
    await _create_type(client, headers, "Tipo Um", group_id)
    tipo_dois = await _create_type(client, headers, "Tipo Dois", group_id)

    response = await client.put(
        f"/api/v1/lawsuit-types/{tipo_dois}",
        json={"name": "Tipo Um", "action_group_id": group_id, "is_active": True},
        headers=headers,
    )

    assert response.status_code == 409


async def test_atualizar_tipo_com_grupo_inexistente_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    group_id = await _create_group(client, headers, "Grupo W")
    type_id = await _create_type(client, headers, "Tipo W", group_id)

    response = await client.put(
        f"/api/v1/lawsuit-types/{type_id}",
        json={"name": "Tipo W", "action_group_id": str(uuid.uuid4()), "is_active": True},
        headers=headers,
    )

    assert response.status_code == 422


async def test_delete_tipo_inexistente_retorna_404(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)

    response = await client.delete(
        f"/api/v1/lawsuit-types/{uuid.uuid4()}", headers=_auth_header(gestor)
    )

    assert response.status_code == 404


async def test_listagem_de_grupos_filtra_por_status(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    ligado_id = await _create_group(client, headers, "Grupo Ligado")
    desligado_id = await _create_group(client, headers, "Grupo Desligado")
    await client.put(
        f"/api/v1/action-groups/{desligado_id}",
        json={"name": "Grupo Desligado", "is_active": False},
        headers=headers,
    )

    response = await client.get(
        "/api/v1/action-groups", params={"status": "inactive"}, headers=headers
    )

    ids = {item["id"] for item in response.json()["items"]}
    assert desligado_id in ids
    assert ligado_id not in ids


async def test_listagem_de_grupos_filtra_por_busca_textual(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    await _create_group(client, headers, "Direito Tributário")
    await _create_group(client, headers, "Direito Cível")

    response = await client.get(
        "/api/v1/action-groups", params={"q": "Tributário"}, headers=headers
    )

    names = {item["name"] for item in response.json()["items"]}
    assert names == {"Direito Tributário"}


async def test_listagem_de_tipos_filtra_por_status(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    group_id = await _create_group(client, headers, "Grupo Com Tipos")
    ligado_id = await _create_type(client, headers, "Tipo Ligado", group_id)
    desligado_id = await _create_type(client, headers, "Tipo Desligado", group_id)
    await client.put(
        f"/api/v1/lawsuit-types/{desligado_id}",
        json={"name": "Tipo Desligado", "action_group_id": group_id, "is_active": False},
        headers=headers,
    )

    response = await client.get(
        "/api/v1/lawsuit-types", params={"status": "inactive"}, headers=headers
    )

    ids = {item["id"] for item in response.json()["items"]}
    assert desligado_id in ids
    assert ligado_id not in ids


async def test_listagem_de_tipos_filtra_por_busca_textual(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    group_id = await _create_group(client, headers, "Grupo Para Busca")
    await _create_type(client, headers, "Reclamatória Trabalhista", group_id)
    await _create_type(client, headers, "Reintegração de Posse", group_id)

    response = await client.get(
        "/api/v1/lawsuit-types", params={"q": "Trabalhista"}, headers=headers
    )

    names = {item["name"] for item in response.json()["items"]}
    assert names == {"Reclamatória Trabalhista"}


async def test_publications_user_id_opcional(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)

    response = await client.post(
        "/api/v1/action-groups", json={"name": "Sem Responsável"}, headers=headers
    )

    assert response.status_code == 201
    assert response.json()["publications_user_id"] is None
