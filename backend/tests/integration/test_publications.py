"""Registro de publicações do DJEN: HTTP, deduplicação e RLS (spec 042, §8)."""

import json
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.core.tokens import create_access_token
from tests.integration.conftest import SeededUser

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "http" / "comunicaapi.pje.jus.br"
SessionFactory = async_sessionmaker[AsyncSession]


def _auth_header(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)
    return {"Authorization": f"Bearer {token}"}


def _fixture_item(index: int = 0) -> dict[str, object]:
    payload = json.loads((FIXTURES / "oab_mg.json").read_text(encoding="utf-8"))
    return payload["items"][index]  # type: ignore[no-any-return]


async def test_importar_publicacao_persiste_filhos(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user()
    item = _fixture_item()

    response = await client.post(
        "/api/v1/publications", json={"item": item}, headers=_auth_header(user)
    )

    assert response.status_code == 201
    body = response.json()
    assert body["external_id"] == item["id"]
    assert body["hash"] == item["hash"]
    assert body["availability_date"] == item["data_disponibilizacao"]
    assert body["process_number"] == item["numero_processo"]


async def test_hash_duplicado_retorna_409(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 2: o hash do DJEN é a chave de deduplicação (regra central do sync da 044)."""
    user = await make_user()
    item = _fixture_item()
    headers = _auth_header(user)

    first = await client.post("/api/v1/publications", json={"item": item}, headers=headers)
    assert first.status_code == 201

    second = await client.post("/api/v1/publications", json={"item": item}, headers=headers)
    assert second.status_code == 409


async def test_item_invalido_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user()
    response = await client.post(
        "/api/v1/publications",
        json={"item": {"siglaTribunal": "TJSP"}},
        headers=_auth_header(user),
    )
    assert response.status_code == 422


async def test_rls_nas_tres_tabelas(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: SessionFactory,
) -> None:
    """Tenant A importa; tenant B não enxerga nada nas três tabelas (CLAUDE.md §4)."""
    user_a = await make_user()
    user_b = await make_user()
    item = _fixture_item(index=1)

    created = await client.post(
        "/api/v1/publications", json={"item": item}, headers=_auth_header(user_a)
    )
    assert created.status_code == 201
    publication_id = created.json()["id"]

    async def count_visible(tenant_id: uuid.UUID, table: str) -> int:
        async with app_session_factory() as session, session.begin():
            await set_tenant_context(session, tenant_id)
            result = await session.execute(text(f"SELECT count(*) FROM {table}"))
            return result.scalar_one()  # type: ignore[no-any-return]

    for table in ("publications", "publication_recipients", "publication_lawyers"):
        assert await count_visible(user_a.tenant_id, table) >= 1
        assert await count_visible(user_b.tenant_id, table) == 0

    # E a FK aponta para a publicação certa (filhos não ficaram órfãos de outro id).
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user_a.tenant_id)
        orphans = await session.execute(
            text("SELECT count(*) FROM publication_recipients " "WHERE publication_id != :pid"),
            {"pid": publication_id},
        )
        assert orphans.scalar_one() == 0
