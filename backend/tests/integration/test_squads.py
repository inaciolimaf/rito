import uuid
from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.core.tokens import create_access_token
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser


def _auth_header(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)
    return {"Authorization": f"Bearer {token}"}


async def test_crud_completo(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    administrador = await make_user(role=UserRole.ADMINISTRADOR)
    membro = await make_user(tenant_id=administrador.tenant_id, role=UserRole.COLABORADOR)
    headers = _auth_header(administrador)

    create_response = await client.post(
        "/api/v1/squads",
        json={"name": "Time Cível", "member_ids": [str(membro.user_id)]},
        headers=headers,
    )
    assert create_response.status_code == 201
    squad_id = create_response.json()["id"]
    assert len(create_response.json()["members"]) == 1
    assert create_response.json()["members"][0]["id"] == str(membro.user_id)

    get_response = await client.get(f"/api/v1/squads/{squad_id}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Time Cível"

    list_response = await client.get("/api/v1/squads", headers=headers)
    assert list_response.status_code == 200
    ids = {item["id"] for item in list_response.json()["items"]}
    assert squad_id in ids

    update_response = await client.put(
        f"/api/v1/squads/{squad_id}",
        json={"name": "Time Cível Renomeado", "is_active": True, "member_ids": []},
        headers=headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Time Cível Renomeado"
    assert update_response.json()["members"] == []

    delete_response = await client.delete(f"/api/v1/squads/{squad_id}", headers=headers)
    assert delete_response.status_code == 204

    get_after_delete = await client.get(f"/api/v1/squads/{squad_id}", headers=headers)
    assert get_after_delete.status_code == 404


async def test_nome_duplicado_retorna_409(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    administrador = await make_user(role=UserRole.ADMINISTRADOR)
    headers = _auth_header(administrador)

    await client.post("/api/v1/squads", json={"name": "Duplicado"}, headers=headers)
    response = await client.post("/api/v1/squads", json={"name": "Duplicado"}, headers=headers)

    assert response.status_code == 409


async def test_renomear_para_nome_ja_existente_retorna_409(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    administrador = await make_user(role=UserRole.ADMINISTRADOR)
    headers = _auth_header(administrador)

    await client.post("/api/v1/squads", json={"name": "Time A"}, headers=headers)
    squad_b = await client.post("/api/v1/squads", json={"name": "Time B"}, headers=headers)

    response = await client.put(
        f"/api/v1/squads/{squad_b.json()['id']}",
        json={"name": "Time A", "is_active": True, "member_ids": []},
        headers=headers,
    )

    assert response.status_code == 409


async def test_reconciliacao_de_membros_no_put(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    administrador = await make_user(role=UserRole.ADMINISTRADOR)
    membro_a = await make_user(tenant_id=administrador.tenant_id, role=UserRole.COLABORADOR)
    membro_b = await make_user(tenant_id=administrador.tenant_id, role=UserRole.COLABORADOR)
    headers = _auth_header(administrador)

    create_response = await client.post(
        "/api/v1/squads",
        json={"name": "Time Reconciliação", "member_ids": [str(membro_a.user_id)]},
        headers=headers,
    )
    squad_id = create_response.json()["id"]

    # PUT sem membro_a e com membro_b: remove o ausente, adiciona o novo.
    update_response = await client.put(
        f"/api/v1/squads/{squad_id}",
        json={
            "name": "Time Reconciliação",
            "is_active": True,
            "member_ids": [str(membro_b.user_id)],
        },
        headers=headers,
    )

    assert update_response.status_code == 200
    member_ids = {member["id"] for member in update_response.json()["members"]}
    assert member_ids == {str(membro_b.user_id)}


async def test_excluir_time_nao_apaga_usuarios(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    administrador = await make_user(role=UserRole.ADMINISTRADOR)
    membro = await make_user(tenant_id=administrador.tenant_id, role=UserRole.COLABORADOR)
    headers = _auth_header(administrador)

    create_response = await client.post(
        "/api/v1/squads",
        json={"name": "Time Efêmero", "member_ids": [str(membro.user_id)]},
        headers=headers,
    )
    squad_id = create_response.json()["id"]

    await client.delete(f"/api/v1/squads/{squad_id}", headers=headers)

    user_response = await client.get(f"/api/v1/users/{membro.user_id}", headers=headers)
    assert user_response.status_code == 200


async def test_remover_membro_nao_apaga_usuario(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    administrador = await make_user(role=UserRole.ADMINISTRADOR)
    membro = await make_user(tenant_id=administrador.tenant_id, role=UserRole.COLABORADOR)
    headers = _auth_header(administrador)

    create_response = await client.post(
        "/api/v1/squads",
        json={"name": "Time Com Remoção", "member_ids": [str(membro.user_id)]},
        headers=headers,
    )
    squad_id = create_response.json()["id"]

    await client.put(
        f"/api/v1/squads/{squad_id}",
        json={"name": "Time Com Remoção", "is_active": True, "member_ids": []},
        headers=headers,
    )

    user_response = await client.get(f"/api/v1/users/{membro.user_id}", headers=headers)
    assert user_response.status_code == 200


async def test_tenant_a_nao_ve_time_de_tenant_b(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    admin_a = await make_user(role=UserRole.ADMINISTRADOR)
    admin_b = await make_user(role=UserRole.ADMINISTRADOR)

    create_response = await client.post(
        "/api/v1/squads", json={"name": "Time Isolado"}, headers=_auth_header(admin_a)
    )
    squad_id = create_response.json()["id"]

    response = await client.get(f"/api/v1/squads/{squad_id}", headers=_auth_header(admin_b))

    assert response.status_code == 404


async def test_colaborador_pode_listar_mas_nao_criar(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    colaborador = await make_user(role=UserRole.COLABORADOR)

    list_response = await client.get("/api/v1/squads", headers=_auth_header(colaborador))
    assert list_response.status_code == 200

    create_response = await client.post(
        "/api/v1/squads", json={"name": "Time Não Autorizado"}, headers=_auth_header(colaborador)
    )
    assert create_response.status_code == 403


async def test_time_pode_ser_criado_vazio(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    administrador = await make_user(role=UserRole.ADMINISTRADOR)

    response = await client.post(
        "/api/v1/squads", json={"name": "Time Vazio"}, headers=_auth_header(administrador)
    )

    assert response.status_code == 201
    assert response.json()["members"] == []


async def test_put_time_inexistente_retorna_404(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    administrador = await make_user(role=UserRole.ADMINISTRADOR)

    response = await client.put(
        f"/api/v1/squads/{uuid.uuid4()}",
        json={"name": "Não Existe", "is_active": True, "member_ids": []},
        headers=_auth_header(administrador),
    )

    assert response.status_code == 404


async def test_delete_time_inexistente_retorna_404(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    administrador = await make_user(role=UserRole.ADMINISTRADOR)

    response = await client.delete(
        f"/api/v1/squads/{uuid.uuid4()}", headers=_auth_header(administrador)
    )

    assert response.status_code == 404


async def test_listagem_filtra_por_busca_textual(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    administrador = await make_user(role=UserRole.ADMINISTRADOR)
    headers = _auth_header(administrador)

    await client.post("/api/v1/squads", json={"name": "Time Trabalhista"}, headers=headers)
    await client.post("/api/v1/squads", json={"name": "Time Tributário"}, headers=headers)

    response = await client.get("/api/v1/squads", params={"q": "Trabalhista"}, headers=headers)

    assert response.status_code == 200
    names = {item["name"] for item in response.json()["items"]}
    assert names == {"Time Trabalhista"}


async def test_listagem_filtra_por_status(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    administrador = await make_user(role=UserRole.ADMINISTRADOR)
    headers = _auth_header(administrador)

    create_response = await client.post(
        "/api/v1/squads", json={"name": "Time Para Inativar"}, headers=headers
    )
    squad_id = create_response.json()["id"]
    await client.put(
        f"/api/v1/squads/{squad_id}",
        json={"name": "Time Para Inativar", "is_active": False, "member_ids": []},
        headers=headers,
    )

    response = await client.get("/api/v1/squads", params={"status": "inactive"}, headers=headers)

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["items"]}
    assert squad_id in ids
    assert all(not item["is_active"] for item in response.json()["items"])


async def test_nome_de_time_colide_ignorando_caixa_e_acento(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Spec 102, regra 13 (dívida nº 11). `squads` era a única das 5 taxonomias em que
    "Time A", "TIME A" e "Timé A" conviviam."""
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    criado = await client.post("/api/v1/squads", json={"name": "Time Ética"}, headers=headers)
    assert criado.status_code == 201, criado.text

    for colidente in ("TIME ÉTICA", "time etica", "Timé Etica"):
        resposta = await client.post("/api/v1/squads", json={"name": colidente}, headers=headers)
        assert resposta.status_code == 409, f"{colidente!r} deveria colidir: {resposta.text}"

    # Nome de fato diferente continua passando.
    outro = await client.post("/api/v1/squads", json={"name": "Time Cível"}, headers=headers)
    assert outro.status_code == 201, outro.text


async def test_renomear_time_para_nome_colidente_retorna_409(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Spec 102, regra 13 no PUT — o mesmo nome dele próprio continua passando."""
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    primeiro = await client.post("/api/v1/squads", json={"name": "Trabalhista"}, headers=headers)
    segundo = await client.post("/api/v1/squads", json={"name": "Previdenciário"}, headers=headers)
    assert primeiro.status_code == 201 and segundo.status_code == 201

    colisao = await client.put(
        f"/api/v1/squads/{segundo.json()['id']}",
        json={"name": "TRABALHISTA", "is_active": True, "member_ids": []},
        headers=headers,
    )
    assert colisao.status_code == 409

    proprio = await client.put(
        f"/api/v1/squads/{segundo.json()['id']}",
        json={"name": "Previdenciário", "is_active": True, "member_ids": []},
        headers=headers,
    )
    assert proprio.status_code == 200
