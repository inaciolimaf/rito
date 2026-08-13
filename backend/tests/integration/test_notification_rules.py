"""Notificações: configuração (spec 069, §4) — regras por evento (Gestor) e
preferências de canal por usuário (qualquer um, só a própria)."""

from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser, auth_header


async def test_lista_regras_sempre_devolve_os_3_eventos(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = auth_header(gestor)

    response = await client.get("/api/v1/notification-rules", headers=headers)
    assert response.status_code == 200
    events = {row["event"] for row in response.json()}
    assert events == {"NOVO_CLIENTE", "NOVO_PROCESSO", "INTIMACAO"}
    assert all(row["responsible_user_id"] is None for row in response.json())


async def test_colaborador_nao_acessa_regras(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    colaborador = await make_user(role=UserRole.COLABORADOR)
    headers = auth_header(colaborador)

    response = await client.get("/api/v1/notification-rules", headers=headers)
    assert response.status_code == 403


async def test_gestor_configura_regra(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = auth_header(gestor)
    responsavel = await make_user(tenant_id=gestor.tenant_id, role=UserRole.COLABORADOR)

    response = await client.put(
        "/api/v1/notification-rules/NOVO_CLIENTE",
        json={"responsible_user_id": str(responsavel.user_id), "channels": ["EMAIL"]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["event"] == "NOVO_CLIENTE"
    assert body["responsible_user_id"] == str(responsavel.user_id)
    assert body["channels"] == ["EMAIL"]

    listed = await client.get("/api/v1/notification-rules", headers=headers)
    updated = next(row for row in listed.json() if row["event"] == "NOVO_CLIENTE")
    assert updated["responsible_user_id"] == str(responsavel.user_id)


async def test_lista_preferencias_sempre_devolve_os_3_canais_habilitados(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    colaborador = await make_user(role=UserRole.COLABORADOR)
    headers = auth_header(colaborador)

    response = await client.get("/api/v1/notification-preferences", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert {row["channel"] for row in body} == {"EMAIL", "SMS", "WHATSAPP"}
    assert all(row["enabled"] is True for row in body)


async def test_usuario_desabilita_canal(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    colaborador = await make_user(role=UserRole.COLABORADOR)
    headers = auth_header(colaborador)

    response = await client.put(
        "/api/v1/notification-preferences/EMAIL",
        json={"enabled": False},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"channel": "EMAIL", "enabled": False}

    listed = await client.get("/api/v1/notification-preferences", headers=headers)
    email_pref = next(row for row in listed.json() if row["channel"] == "EMAIL")
    assert email_pref["enabled"] is False
