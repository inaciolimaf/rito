"""Modelos: editor (spec 065, §8) — cabeçalho/rodapé/marca d'água persistem junto do
modelo e o conteúdo HTML salva e reabre idêntico, char a char (regra 4)."""

from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.core.tokens import create_access_token
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser

_RICH_HTML = (
    "<h1>Título</h1><p><strong>Negrito</strong> e <em>itálico</em> e "
    '<a href="https://exemplo.com">link</a>.</p>'
    "<table><tbody><tr><td>Célula 1</td><td>Célula 2</td></tr></tbody></table>"
    '<ul data-type="taskList"><li data-checked="false">Item</li></ul><hr>'
)


def _auth_header(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)
    return {"Authorization": f"Bearer {token}"}


async def test_put_grava_cabecalho_rodape_e_marca_dagua(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.COLABORADOR)
    headers = _auth_header(user)

    created = await client.post(
        "/api/v1/templates",
        json={"name": "Modelo com moldura", "type": "CONTRATO", "content": "<p>corpo</p>"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    template_id = created.json()["id"]
    assert created.json()["header_content"] == ""
    assert created.json()["footer_content"] == ""
    assert created.json()["watermark_text"] is None

    updated = await client.put(
        f"/api/v1/templates/{template_id}",
        json={
            "name": "Modelo com moldura",
            "type": "CONTRATO",
            "content": "<p>corpo</p>",
            "header_content": "<p>Escritório Modelo Ltda.</p>",
            "footer_content": "<p>Página confidencial</p>",
            "watermark_text": "MINUTA",
        },
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["header_content"] == "<p>Escritório Modelo Ltda.</p>"
    assert body["footer_content"] == "<p>Página confidencial</p>"
    assert body["watermark_text"] == "MINUTA"

    fetched = await client.get(f"/api/v1/templates/{template_id}", headers=headers)
    assert fetched.json()["watermark_text"] == "MINUTA"


async def test_conteudo_html_complexo_salva_e_reabre_identico(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.COLABORADOR)
    headers = _auth_header(user)

    created = await client.post(
        "/api/v1/templates",
        json={"name": "Modelo rico", "type": "PETICAO", "content": _RICH_HTML},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    template_id = created.json()["id"]
    assert created.json()["content"] == _RICH_HTML

    fetched = await client.get(f"/api/v1/templates/{template_id}", headers=headers)
    assert fetched.json()["content"] == _RICH_HTML


async def test_duplicar_leva_cabecalho_rodape_e_marca_dagua(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.COLABORADOR)
    headers = _auth_header(user)

    created = await client.post(
        "/api/v1/templates",
        json={
            "name": "Original",
            "type": "DOCUMENTO",
            "content": "<p>corpo</p>",
            "header_content": "<p>Cabeçalho</p>",
            "footer_content": "<p>Rodapé</p>",
            "watermark_text": "RASCUNHO",
        },
        headers=headers,
    )
    template_id = created.json()["id"]

    duplicate = await client.post(f"/api/v1/templates/{template_id}/duplicate", headers=headers)
    assert duplicate.status_code == 201, duplicate.text
    body = duplicate.json()
    assert body["header_content"] == "<p>Cabeçalho</p>"
    assert body["footer_content"] == "<p>Rodapé</p>"
    assert body["watermark_text"] == "RASCUNHO"
