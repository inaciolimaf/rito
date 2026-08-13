"""Modelos: engine de variáveis (spec 066, §8) — resolução real contra cliente/
processo/escritório/usuário, ausência de escopo e isolamento por tenant."""

from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.core.tokens import create_access_token
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuits import (
    _create_customer,
    _create_lawsuit,
    _create_lawsuit_type,
    _create_stage,
)


def _auth_header(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)
    return {"Authorization": f"Bearer {token}"}


async def _create_account(client: AsyncClient, headers: dict[str, str]) -> None:
    payload = {
        "name": "Escritório Teste Ltda",
        "alternate_name": "Escritório Teste",
        "identification": "11.222.333/0001-81",
        "country": "BRASIL",
        "state": "SP",
        "city": "São Paulo",
        "postal_code": "01310-100",
        "street": "Av. Paulista, 1000",
        "region": "Bela Vista",
        "cellphone": "11999998888",
        "phone": "1130004000",
        "email": "contato@escritorioteste.com.br",
        "email_admin": "financeiro@escritorioteste.com.br",
        "timezone": "America/Sao_Paulo",
    }
    response = await client.put("/api/v1/account", json=payload, headers=headers)
    assert response.status_code == 200, response.text


async def _create_template(client: AsyncClient, headers: dict[str, str], content: str) -> str:
    response = await client.post(
        "/api/v1/templates",
        json={"name": "Modelo de teste", "type": "CONTRATO", "content": content},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    result: str = response.json()["id"]
    return result


async def test_catalogo_de_variaveis_lista_os_4_namespaces(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(user)

    response = await client.get("/api/v1/template-variables", headers=headers)
    assert response.status_code == 200, response.text
    namespaces = {item["namespace"] for item in response.json()}
    assert namespaces == {"cliente", "processo", "escritorio", "usuario"}


async def test_resolucao_real_um_campo_de_cada_namespace(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(user)
    await _create_account(client, headers)

    customer_id = await _create_customer(client, headers, "Maria da Silva")
    lawsuit_type_id, _group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    lawsuit = await _create_lawsuit(
        client,
        headers,
        user_id=str(user.user_id),
        lawsuit_type_id=lawsuit_type_id,
        stage_id=stage_id,
        process_number="0001234-34.2026.8.26.0100",
    )
    lawsuit_id = str(lawsuit["id"])

    template_id = await _create_template(
        client,
        headers,
        "<p>{{cliente.nome_completo}} · {{processo.numero_cnj}} · "
        "{{escritorio.razao_social}} · {{usuario.nome}}</p>",
    )

    response = await client.post(
        f"/api/v1/templates/{template_id}/resolve",
        json={"customer_id": customer_id, "lawsuit_id": lawsuit_id},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "Maria da Silva" in body["content"]
    assert "0001234-34.2026.8.26.0100" in body["content"]
    assert "Escritório Teste Ltda" in body["content"]
    assert "Usuário de Teste" in body["content"]
    assert body["missing"] == []


async def test_sem_customer_id_variavel_de_cliente_fica_ausente_resto_resolve(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(user)
    await _create_account(client, headers)

    template_id = await _create_template(
        client, headers, "<p>{{cliente.nome_completo}} — {{escritorio.razao_social}}</p>"
    )

    response = await client.post(
        f"/api/v1/templates/{template_id}/resolve", json={}, headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["missing"] == ["cliente.nome_completo"]
    assert "Escritório Teste Ltda" in body["content"]
    assert '<mark data-missing="true">{{cliente.nome_completo}}</mark>' in body["content"]


async def test_customer_id_de_outro_tenant_retorna_404(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user_a = await make_user(role=UserRole.GESTOR)
    headers_a = _auth_header(user_a)
    customer_id = await _create_customer(client, headers_a, "Cliente do tenant A")

    user_b = await make_user(role=UserRole.GESTOR)
    headers_b = _auth_header(user_b)
    template_id = await _create_template(client, headers_b, "<p>{{cliente.nome_completo}}</p>")

    response = await client.post(
        f"/api/v1/templates/{template_id}/resolve",
        json={"customer_id": customer_id},
        headers=headers_b,
    )
    assert response.status_code == 404
