import uuid
from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.tokens import create_access_token
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser

_SEED_INSERT_SQL = """
    INSERT INTO customer_origins (tenant_id, name)
    SELECT t.id, o.name
    FROM tenants t
    CROSS JOIN (VALUES ('ANÚNCIO'), ('ESCRITÓRIO'), ('FACEBOOK'), ('GOOGLE'), ('INDICAÇÃO'),
                        ('INSTAGRAM'), ('PARTE CONTRÁRIA'), ('SITE DO ESCRITÓRIO')) AS o(name)
    WHERE t.id = :tenant_id
    ON CONFLICT (tenant_id, immutable_unaccent(lower(name))) DO NOTHING
    """


def _auth_header(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)
    return {"Authorization": f"Bearer {token}"}


async def _create_origin(client: AsyncClient, headers: dict[str, str], name: str) -> str:
    response = await client.post("/api/v1/customer-origins", json={"name": name}, headers=headers)
    assert response.status_code == 201
    result: str = response.json()["id"]
    return result


async def test_crud(client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)

    origin_id = await _create_origin(client, headers, "Indicação de Cliente")

    list_response = await client.get("/api/v1/customer-origins", headers=headers)
    assert list_response.status_code == 200
    assert any(item["id"] == origin_id for item in list_response.json()["items"])

    update_response = await client.put(
        f"/api/v1/customer-origins/{origin_id}",
        json={"name": "Indicação Renomeada", "is_active": True},
        headers=headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Indicação Renomeada"

    delete_response = await client.delete(f"/api/v1/customer-origins/{origin_id}", headers=headers)
    assert delete_response.status_code == 204


async def test_nome_duplicado_ignorando_acento_retorna_409(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    await _create_origin(client, headers, "Indicação")

    response = await client.post(
        "/api/v1/customer-origins", json={"name": "INDICACAO"}, headers=headers
    )

    assert response.status_code == 409


async def _create_customer(client: AsyncClient, headers: dict[str, str], origin_id: str) -> str:
    response = await client.post(
        "/api/v1/customers",
        json={"type": "PF", "name": f"Cliente {uuid.uuid4().hex[:8]}", "origin_id": origin_id},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    result: str = response.json()["id"]
    return result


async def test_excluir_origem_sem_contato_continua_204(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Spec 101, regra 3: a guarda não muda o caminho feliz."""
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem Solta")

    response = await client.delete(f"/api/v1/customer-origins/{origin_id}", headers=headers)

    assert response.status_code == 204


async def test_excluir_origem_em_uso_retorna_409_e_nao_apaga(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Spec 101, regra 3 — fecha a dívida nº 13. Antes desta spec o DELETE violava a FK
    `customers.origin_id` e virava 500."""
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem Ocupada")
    await _create_customer(client, headers, origin_id)

    response = await client.delete(f"/api/v1/customer-origins/{origin_id}", headers=headers)

    assert response.status_code == 409
    assert "transfira" in response.json()["detail"].lower()
    listing = await client.get("/api/v1/customer-origins", headers=headers)
    assert origin_id in [item["id"] for item in listing.json()["items"]]


async def test_transferencia_reatribui_contatos_e_libera_a_exclusao(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Spec 101, regra 4: `transferred_count` deixa de ser o 0 fixo do stub."""
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origem = await _create_origin(client, headers, "Origem Ocupada")
    destino = await _create_origin(client, headers, "Destino")
    customer_id = await _create_customer(client, headers, origem)

    transfer = await client.post(
        "/api/v1/customer-origins/transfer",
        json={"from_id": origem, "to_id": destino},
        headers=headers,
    )

    assert transfer.status_code == 200
    assert transfer.json()["transferred_count"] == 1

    moved = await client.get(f"/api/v1/customers/{customer_id}", headers=headers)
    assert moved.json()["origin_id"] == destino

    liberada = await client.delete(f"/api/v1/customer-origins/{origem}", headers=headers)
    assert liberada.status_code == 204


async def test_transferencia_com_ids_validos_retorna_200(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origem = await _create_origin(client, headers, "Origem")
    destino = await _create_origin(client, headers, "Destino")

    response = await client.post(
        "/api/v1/customer-origins/transfer",
        json={"from_id": origem, "to_id": destino},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["transferred_count"] == 0


async def test_transferencia_com_ids_iguais_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Sozinha")

    response = await client.post(
        "/api/v1/customer-origins/transfer",
        json={"from_id": origin_id, "to_id": origin_id},
        headers=headers,
    )

    assert response.status_code == 422


async def test_transferencia_com_origem_inexistente_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Existente")

    response = await client.post(
        "/api/v1/customer-origins/transfer",
        json={"from_id": origin_id, "to_id": str(uuid.uuid4())},
        headers=headers,
    )

    assert response.status_code == 422


async def test_colaborador_recebe_403_ao_escrever(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    colaborador = await make_user(role=UserRole.COLABORADOR)
    headers = _auth_header(colaborador)

    list_response = await client.get("/api/v1/customer-origins", headers=headers)
    assert list_response.status_code == 200

    create_response = await client.post(
        "/api/v1/customer-origins", json={"name": "Não Autorizada"}, headers=headers
    )
    assert create_response.status_code == 403


async def test_tenant_a_nao_ve_origem_de_tenant_b(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor_a = await make_user(role=UserRole.GESTOR)
    gestor_b = await make_user(role=UserRole.GESTOR)

    origin_id = await _create_origin(client, _auth_header(gestor_a), "Isolada")

    response = await client.get("/api/v1/customer-origins", headers=_auth_header(gestor_b))

    ids = {item["id"] for item in response.json()["items"]}
    assert origin_id not in ids


async def test_put_origem_inexistente_retorna_404(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)

    response = await client.put(
        f"/api/v1/customer-origins/{uuid.uuid4()}",
        json={"name": "Não Existe", "is_active": True},
        headers=_auth_header(gestor),
    )

    assert response.status_code == 404


async def test_delete_origem_inexistente_retorna_404(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)

    response = await client.delete(
        f"/api/v1/customer-origins/{uuid.uuid4()}", headers=_auth_header(gestor)
    )

    assert response.status_code == 404


async def test_renomear_para_nome_existente_retorna_409(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    await _create_origin(client, headers, "Origem Um")
    origem_dois = await _create_origin(client, headers, "Origem Dois")

    response = await client.put(
        f"/api/v1/customer-origins/{origem_dois}",
        json={"name": "Origem Um", "is_active": True},
        headers=headers,
    )

    assert response.status_code == 409


async def test_listagem_filtra_por_status(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    ligada_id = await _create_origin(client, headers, "Origem Ligada")
    desligada_id = await _create_origin(client, headers, "Origem Desligada")
    await client.put(
        f"/api/v1/customer-origins/{desligada_id}",
        json={"name": "Origem Desligada", "is_active": False},
        headers=headers,
    )

    response = await client.get(
        "/api/v1/customer-origins", params={"status": "inactive"}, headers=headers
    )

    ids = {item["id"] for item in response.json()["items"]}
    assert desligada_id in ids
    assert ligada_id not in ids


async def test_listagem_filtra_por_busca_textual(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    await _create_origin(client, headers, "Facebook Ads")
    await _create_origin(client, headers, "Google Ads")

    response = await client.get(
        "/api/v1/customer-origins", params={"q": "Facebook"}, headers=headers
    )

    names = {item["name"] for item in response.json()["items"]}
    assert names == {"Facebook Ads"}


async def test_seed_idempotente(admin_engine: AsyncEngine) -> None:
    """Plano da spec 016: rodar o INSERT de seed duas vezes para o mesmo tenant não
    duplica — o `ON CONFLICT ... DO NOTHING` da migration é real, testado contra o
    Postgres de verdade (mesma SQL da migration 016, ver Descobertas)."""
    tenant_id = uuid.uuid4()
    async with admin_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO tenants (id, slug, name) VALUES (:id, :slug, 'Tenant Seed')"),
            {"id": tenant_id, "slug": f"tenant-seed-{tenant_id}"},
        )
        await conn.execute(text(_SEED_INSERT_SQL), {"tenant_id": tenant_id})
        await conn.execute(text(_SEED_INSERT_SQL), {"tenant_id": tenant_id})

        count = await conn.scalar(
            text("SELECT count(*) FROM customer_origins WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        )

    assert count == 8
