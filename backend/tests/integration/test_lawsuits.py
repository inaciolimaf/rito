import uuid
from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.core.tokens import create_access_token
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser

# Fase 1 = Marketing, fase 2 = Negociação (seed da migration 015) — mesma convenção de
# test_stages.py.
_MARKETING_STEP_ID = 1
_NEGOCIACAO_STEP_ID = 2


def _auth_header(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)
    return {"Authorization": f"Bearer {token}"}


async def _create_lawsuit_type(client: AsyncClient, headers: dict[str, str]) -> tuple[str, str]:
    """Cria grupo + tipo de ação, devolve `(lawsuit_type_id, action_group_id)`."""
    suffix = uuid.uuid4().hex[:8]
    group_response = await client.post(
        "/api/v1/action-groups", json={"name": f"Grupo {suffix}"}, headers=headers
    )
    assert group_response.status_code == 201
    group_id: str = group_response.json()["id"]

    type_response = await client.post(
        "/api/v1/lawsuit-types",
        json={"name": f"Tipo {suffix}", "action_group_id": group_id},
        headers=headers,
    )
    assert type_response.status_code == 201
    type_id: str = type_response.json()["id"]
    return type_id, group_id


async def _create_stage(
    client: AsyncClient, headers: dict[str, str], step_id: int = _MARKETING_STEP_ID
) -> str:
    suffix = uuid.uuid4().hex[:8]
    response = await client.post(
        "/api/v1/stages", json={"name": f"Etapa {suffix}", "step_id": step_id}, headers=headers
    )
    assert response.status_code == 201
    result: str = response.json()["id"]
    return result


async def _find_court_id(client: AsyncClient, headers: dict[str, str], code: str) -> int:
    response = await client.get("/api/v1/courts", params={"q": code}, headers=headers)
    item = next(court for court in response.json() if court["code"] == code)
    result: int = item["id"]
    return result


async def _find_system_id(client: AsyncClient, headers: dict[str, str], name: str) -> int:
    response = await client.get("/api/v1/court-systems", headers=headers)
    item = next(system for system in response.json() if system["name"] == name)
    result: int = item["id"]
    return result


async def _create_lawsuit(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    user_id: str,
    lawsuit_type_id: str,
    stage_id: str,
    **extra: object,
) -> dict[str, object]:
    # Spec 023 regra 1: processo exige no mínimo 1 parte — o helper cria um contato e o
    # vincula como polo ATIVO por padrão; quem precisa de outra composição passa `parties`.
    if "parties" not in extra:
        customer_id = await _create_customer(client, headers, f"Cliente {uuid.uuid4().hex[:8]}")
        extra["parties"] = [{"customer_id": customer_id, "pole": "ATIVO", "is_client": True}]
    payload = {
        "user_id": user_id,
        "lawsuit_type_id": lawsuit_type_id,
        "stage_id": stage_id,
        **extra,
    }
    response = await client.post("/api/v1/lawsuits", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    result: dict[str, object] = response.json()
    return result


async def _create_customer(client: AsyncClient, headers: dict[str, str], name: str) -> str:
    origin_response = await client.post(
        "/api/v1/customer-origins", json={"name": f"Origem {uuid.uuid4().hex[:8]}"}, headers=headers
    )
    assert origin_response.status_code == 201
    response = await client.post(
        "/api/v1/customers",
        json={"type": "PF", "name": name, "origin_id": origin_response.json()["id"]},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    result: str = response.json()["id"]
    return result


async def test_crud_completo(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    type_id, _group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)

    created = await _create_lawsuit(
        client,
        headers,
        user_id=str(gestor.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
        folder="Pasta 1",
        notes="Observação inicial",
    )
    lawsuit_id = created["id"]

    get_response = await client.get(f"/api/v1/lawsuits/{lawsuit_id}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["folder"] == "Pasta 1"

    update_response = await client.put(
        f"/api/v1/lawsuits/{lawsuit_id}",
        json={
            "user_id": str(gestor.user_id),
            "lawsuit_type_id": type_id,
            "stage_id": stage_id,
            "notes": "Observação atualizada",
        },
        headers=headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["notes"] == "Observação atualizada"

    admin = await make_user(role=UserRole.ADMINISTRADOR, tenant_id=gestor.tenant_id)
    delete_response = await client.delete(
        f"/api/v1/lawsuits/{lawsuit_id}", headers=_auth_header(admin)
    )
    assert delete_response.status_code == 204


async def test_grupo_derivado_do_tipo(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    type_id, group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)

    created = await _create_lawsuit(
        client, headers, user_id=str(gestor.user_id), lawsuit_type_id=type_id, stage_id=stage_id
    )

    assert created["action_group_id"] == group_id
    assert created["step_id"] == _MARKETING_STEP_ID


async def test_enviar_action_group_id_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    type_id, group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)

    response = await client.post(
        "/api/v1/lawsuits",
        json={
            "user_id": str(gestor.user_id),
            "lawsuit_type_id": type_id,
            "stage_id": stage_id,
            "action_group_id": group_id,
        },
        headers=headers,
    )

    assert response.status_code == 422


async def test_enviar_step_id_retorna_422(
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
            "step_id": _MARKETING_STEP_ID,
        },
        headers=headers,
    )

    assert response.status_code == 422


async def test_folder_com_31_caracteres_retorna_422(
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
            "folder": "x" * 31,
        },
        headers=headers,
    )

    assert response.status_code == 422


async def test_trocar_etapa_muda_a_fase_derivada(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    type_id, _group_id = await _create_lawsuit_type(client, headers)
    marketing_stage = await _create_stage(client, headers, _MARKETING_STEP_ID)
    negociacao_stage = await _create_stage(client, headers, _NEGOCIACAO_STEP_ID)

    created = await _create_lawsuit(
        client,
        headers,
        user_id=str(gestor.user_id),
        lawsuit_type_id=type_id,
        stage_id=marketing_stage,
    )
    assert created["step_id"] == _MARKETING_STEP_ID

    update_response = await client.put(
        f"/api/v1/lawsuits/{created['id']}",
        json={
            "user_id": str(gestor.user_id),
            "lawsuit_type_id": type_id,
            "stage_id": negociacao_stage,
        },
        headers=headers,
    )

    assert update_response.status_code == 200
    assert update_response.json()["step_id"] == _NEGOCIACAO_STEP_ID


async def test_sistema_incompativel_com_tribunal_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    type_id, _group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)

    # TJPR PROJUDI só tem vínculo com o sistema PROJUDI (spec 021) — ESAJ é incompatível.
    court_id = await _find_court_id(client, headers, "TJPR PROJUDI")
    incompatible_system_id = await _find_system_id(client, headers, "ESAJ")

    response = await client.post(
        "/api/v1/lawsuits",
        json={
            "user_id": str(gestor.user_id),
            "lawsuit_type_id": type_id,
            "stage_id": stage_id,
            "court_id": court_id,
            "court_system_id": incompatible_system_id,
        },
        headers=headers,
    )

    assert response.status_code == 422


async def test_sistema_compativel_com_tribunal_e_aceito(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    type_id, _group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)

    court_id = await _find_court_id(client, headers, "TJPR PROJUDI")
    compatible_system_id = await _find_system_id(client, headers, "PROJUDI")

    created = await _create_lawsuit(
        client,
        headers,
        user_id=str(gestor.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
        court_id=court_id,
        court_system_id=compatible_system_id,
    )

    assert created["court_id"] == court_id
    assert created["court_system_id"] == compatible_system_id


async def test_responsavel_inativo_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    inactive = await make_user(
        role=UserRole.COLABORADOR, tenant_id=gestor.tenant_id, is_active=False
    )
    type_id, _group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)

    response = await client.post(
        "/api/v1/lawsuits",
        json={
            "user_id": str(inactive.user_id),
            "lawsuit_type_id": type_id,
            "stage_id": stage_id,
        },
        headers=headers,
    )

    assert response.status_code == 422


async def test_delete_arquiva(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    admin = await make_user(role=UserRole.ADMINISTRADOR, tenant_id=gestor.tenant_id)
    headers = _auth_header(gestor)
    type_id, _group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)

    created = await _create_lawsuit(
        client, headers, user_id=str(gestor.user_id), lawsuit_type_id=type_id, stage_id=stage_id
    )

    delete_response = await client.delete(
        f"/api/v1/lawsuits/{created['id']}", headers=_auth_header(admin)
    )
    assert delete_response.status_code == 204

    get_response = await client.get(f"/api/v1/lawsuits/{created['id']}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["is_archived"] is True


async def test_colaborador_recebe_403_ao_excluir(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    colaborador = await make_user(role=UserRole.COLABORADOR, tenant_id=gestor.tenant_id)
    headers = _auth_header(gestor)
    type_id, _group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)

    created = await _create_lawsuit(
        client, headers, user_id=str(gestor.user_id), lawsuit_type_id=type_id, stage_id=stage_id
    )

    response = await client.delete(
        f"/api/v1/lawsuits/{created['id']}", headers=_auth_header(colaborador)
    )
    assert response.status_code == 403


async def test_tenant_a_nao_ve_processo_de_tenant_b(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor_a = await make_user(role=UserRole.GESTOR)
    headers_a = _auth_header(gestor_a)
    type_id, _group_id = await _create_lawsuit_type(client, headers_a)
    stage_id = await _create_stage(client, headers_a)
    created = await _create_lawsuit(
        client,
        headers_a,
        user_id=str(gestor_a.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
    )

    gestor_b = await make_user(role=UserRole.GESTOR)
    response = await client.get(f"/api/v1/lawsuits/{created['id']}", headers=_auth_header(gestor_b))

    assert response.status_code == 404


async def test_get_processo_inexistente_retorna_404(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)

    response = await client.get(f"/api/v1/lawsuits/{uuid.uuid4()}", headers=_auth_header(gestor))

    assert response.status_code == 404


async def test_criar_com_tipo_inexistente_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    stage_id = await _create_stage(client, headers)

    response = await client.post(
        "/api/v1/lawsuits",
        json={
            "user_id": str(gestor.user_id),
            "lawsuit_type_id": str(uuid.uuid4()),
            "stage_id": stage_id,
        },
        headers=headers,
    )

    assert response.status_code == 422


async def test_criar_com_etapa_inexistente_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    type_id, _group_id = await _create_lawsuit_type(client, headers)

    response = await client.post(
        "/api/v1/lawsuits",
        json={
            "user_id": str(gestor.user_id),
            "lawsuit_type_id": type_id,
            "stage_id": str(uuid.uuid4()),
        },
        headers=headers,
    )

    assert response.status_code == 422


async def test_process_number_guardado_so_com_digitos(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    type_id, _group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)

    created = await _create_lawsuit(
        client,
        headers,
        user_id=str(gestor.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
        process_number="0001234-34.2026.8.26.0100",
    )

    assert created["process_number"] == "00012343420268260100"


async def test_criar_processo_dispara_novo_processo_quando_configurado(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    rule_response = await client.put(
        "/api/v1/notification-rules/NOVO_PROCESSO",
        json={"responsible_user_id": str(gestor.user_id), "channels": []},
        headers=headers,
    )
    assert rule_response.status_code == 200, rule_response.text

    type_id, _group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    await _create_lawsuit(
        client, headers, user_id=str(gestor.user_id), lawsuit_type_id=type_id, stage_id=stage_id
    )

    notifications = await client.get("/api/v1/notifications", headers=headers)
    assert notifications.status_code == 200
    kinds = {item["kind"] for item in notifications.json()["items"]}
    assert "NOVO_PROCESSO" in kinds
