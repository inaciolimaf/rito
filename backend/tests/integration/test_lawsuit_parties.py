import uuid
from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuits import (
    _auth_header,
    _create_customer,
    _create_lawsuit,
    _create_lawsuit_type,
    _create_stage,
)


async def _setup(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> tuple[SeededUser, dict[str, str], dict[str, object]]:
    """Gestor + processo com uma parte (cliente no polo ATIVO), pronto para os cenários."""
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    type_id, _group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    lawsuit = await _create_lawsuit(
        client,
        headers,
        user_id=str(gestor.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
    )
    return gestor, headers, lawsuit


async def test_criar_processo_com_cliente_e_contraria(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    type_id, _group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    cliente_id = await _create_customer(client, headers, "Ana Cliente")
    contraria_id = await _create_customer(client, headers, "Carlos Contrário")

    lawsuit = await _create_lawsuit(
        client,
        headers,
        user_id=str(gestor.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
        parties=[
            {"customer_id": contraria_id, "pole": "CONTRARIA", "is_client": False},
            {"customer_id": cliente_id, "pole": "ATIVO", "is_client": True},
        ],
    )

    response = await client.get(f"/api/v1/lawsuits/{lawsuit['id']}/parties", headers=headers)
    assert response.status_code == 200
    parties = response.json()
    assert len(parties) == 2
    # Regra 7: ATIVO antes de CONTRARIA, independente da ordem de criação.
    assert parties[0]["customer_name"] == "Ana Cliente"
    assert parties[0]["pole"] == "ATIVO"
    assert parties[0]["is_client"] is True
    assert parties[1]["customer_name"] == "Carlos Contrário"
    assert parties[1]["pole"] == "CONTRARIA"
    assert parties[1]["is_client"] is False


async def test_criar_processo_sem_parte_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    type_id, _group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)

    response = await client.post(
        "/api/v1/lawsuits",
        json={
            "user_id": str(gestor.user_id),
            "lawsuit_type_id": type_id,
            "stage_id": stage_id,
        },
        headers=headers,
    )
    assert response.status_code == 422

    response = await client.post(
        "/api/v1/lawsuits",
        json={
            "user_id": str(gestor.user_id),
            "lawsuit_type_id": type_id,
            "stage_id": stage_id,
            "parties": [],
        },
        headers=headers,
    )
    assert response.status_code == 422


async def test_criar_processo_com_contato_inexistente_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    type_id, _group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)

    response = await client.post(
        "/api/v1/lawsuits",
        json={
            "user_id": str(gestor.user_id),
            "lawsuit_type_id": type_id,
            "stage_id": stage_id,
            "parties": [{"customer_id": str(uuid.uuid4()), "pole": "ATIVO", "is_client": True}],
        },
        headers=headers,
    )
    assert response.status_code == 422


async def test_remover_ultima_parte_retorna_409(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers, lawsuit = await _setup(client, make_user)
    parties = (
        await client.get(f"/api/v1/lawsuits/{lawsuit['id']}/parties", headers=headers)
    ).json()
    assert len(parties) == 1

    response = await client.delete(
        f"/api/v1/lawsuits/{lawsuit['id']}/parties/{parties[0]['id']}", headers=headers
    )
    assert response.status_code == 409


async def test_mesma_pessoa_em_dois_polos_e_aceita(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    type_id, _group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    customer_id = await _create_customer(client, headers, "Herdeiro Inventariante")

    lawsuit = await _create_lawsuit(
        client,
        headers,
        user_id=str(gestor.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
        parties=[
            {"customer_id": customer_id, "pole": "ATIVO", "is_client": True},
            {"customer_id": customer_id, "pole": "TERCEIRO", "is_client": True},
        ],
    )

    parties = (
        await client.get(f"/api/v1/lawsuits/{lawsuit['id']}/parties", headers=headers)
    ).json()
    assert {party["pole"] for party in parties} == {"ATIVO", "TERCEIRO"}


async def test_mesma_pessoa_no_mesmo_polo_retorna_409(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers, lawsuit = await _setup(client, make_user)
    parties = (
        await client.get(f"/api/v1/lawsuits/{lawsuit['id']}/parties", headers=headers)
    ).json()
    customer_id = parties[0]["customer_id"]

    # Via endpoint dedicado: mesma pessoa, mesmo polo → 409.
    response = await client.post(
        f"/api/v1/lawsuits/{lawsuit['id']}/parties",
        json={"customer_id": customer_id, "pole": "ATIVO", "is_client": True},
        headers=headers,
    )
    assert response.status_code == 409

    # No payload de criação de um novo processo: duplicata interna → 409.
    type_id, _group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    create_response = await client.post(
        "/api/v1/lawsuits",
        json={
            "user_id": str(_gestor.user_id),
            "lawsuit_type_id": type_id,
            "stage_id": stage_id,
            "parties": [
                {"customer_id": customer_id, "pole": "ATIVO", "is_client": True},
                {"customer_id": customer_id, "pole": "ATIVO", "is_client": True},
            ],
        },
        headers=headers,
    )
    assert create_response.status_code == 409


async def test_trocar_polo(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers, lawsuit = await _setup(client, make_user)
    parties = (
        await client.get(f"/api/v1/lawsuits/{lawsuit['id']}/parties", headers=headers)
    ).json()
    party_id = parties[0]["id"]

    response = await client.put(
        f"/api/v1/lawsuits/{lawsuit['id']}/parties/{party_id}",
        json={"pole": "PASSIVO"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["pole"] == "PASSIVO"

    # Trocar para um polo onde a pessoa já está → 409.
    await client.post(
        f"/api/v1/lawsuits/{lawsuit['id']}/parties",
        json={"customer_id": parties[0]["customer_id"], "pole": "CONTRARIA", "is_client": False},
        headers=headers,
    )
    conflict = await client.put(
        f"/api/v1/lawsuits/{lawsuit['id']}/parties/{party_id}",
        json={"pole": "CONTRARIA"},
        headers=headers,
    )
    assert conflict.status_code == 409


async def test_remover_parte_quando_ha_outras(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers, lawsuit = await _setup(client, make_user)
    extra_id = await _create_customer(client, headers, "Segundo Cliente")
    await client.post(
        f"/api/v1/lawsuits/{lawsuit['id']}/parties",
        json={"customer_id": extra_id, "pole": "ATIVO", "is_client": True},
        headers=headers,
    )
    parties = (
        await client.get(f"/api/v1/lawsuits/{lawsuit['id']}/parties", headers=headers)
    ).json()
    assert len(parties) == 2

    response = await client.delete(
        f"/api/v1/lawsuits/{lawsuit['id']}/parties/{parties[0]['id']}", headers=headers
    )
    assert response.status_code == 204
    remaining = (
        await client.get(f"/api/v1/lawsuits/{lawsuit['id']}/parties", headers=headers)
    ).json()
    assert len(remaining) == 1


async def test_excluir_processo_nao_apaga_contatos(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor, headers, lawsuit = await _setup(client, make_user)
    admin = await make_user(role=UserRole.ADMINISTRADOR, tenant_id=gestor.tenant_id)
    parties = (
        await client.get(f"/api/v1/lawsuits/{lawsuit['id']}/parties", headers=headers)
    ).json()
    customer_id = parties[0]["customer_id"]

    delete_response = await client.delete(
        f"/api/v1/lawsuits/{lawsuit['id']}", headers=_auth_header(admin)
    )
    assert delete_response.status_code == 204

    # Regra 5: o contato nunca é apagado junto com o processo.
    customer_response = await client.get(f"/api/v1/customers/{customer_id}", headers=headers)
    assert customer_response.status_code == 200

    # Delete é soft (spec 022): os vínculos continuam consultáveis.
    parties_response = await client.get(
        f"/api/v1/lawsuits/{lawsuit['id']}/parties", headers=headers
    )
    assert parties_response.status_code == 200
    assert len(parties_response.json()) == 1


async def test_arquivar_contato_nao_remove_dos_processos(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers, lawsuit = await _setup(client, make_user)
    parties = (
        await client.get(f"/api/v1/lawsuits/{lawsuit['id']}/parties", headers=headers)
    ).json()
    customer_id = parties[0]["customer_id"]

    archive_response = await client.delete(f"/api/v1/customers/{customer_id}", headers=headers)
    assert archive_response.status_code == 204

    # Regra 6: contato arquivado continua vinculado ao processo.
    parties_response = await client.get(
        f"/api/v1/lawsuits/{lawsuit['id']}/parties", headers=headers
    )
    assert parties_response.status_code == 200
    assert len(parties_response.json()) == 1


async def test_partes_isoladas_entre_tenants(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor_a, headers_a, lawsuit = await _setup(client, make_user)
    parties = (
        await client.get(f"/api/v1/lawsuits/{lawsuit['id']}/parties", headers=headers_a)
    ).json()
    party_id = parties[0]["id"]

    gestor_b = await make_user(role=UserRole.GESTOR)
    headers_b = _auth_header(gestor_b)

    # Tenant B não lista, não altera e não remove a parte de tenant A.
    list_response = await client.get(f"/api/v1/lawsuits/{lawsuit['id']}/parties", headers=headers_b)
    assert list_response.status_code == 404
    update_response = await client.put(
        f"/api/v1/lawsuits/{lawsuit['id']}/parties/{party_id}",
        json={"pole": "PASSIVO"},
        headers=headers_b,
    )
    assert update_response.status_code == 404
    delete_response = await client.delete(
        f"/api/v1/lawsuits/{lawsuit['id']}/parties/{party_id}", headers=headers_b
    )
    assert delete_response.status_code == 404
