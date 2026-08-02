"""ck_cycle direto no banco (spec 030, checklist de cobertura): os testes da 024 cobrem
o 422 da camada Pydantic; aqui quem barra é o próprio CheckConstraint — um UPDATE cru,
sem schema na frente, tem que levantar IntegrityError."""

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuits_listing import LawsuitFactory, _make_factory


@pytest.fixture
async def factory(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> LawsuitFactory:
    return await _make_factory(client, make_user, app_session_factory)


async def test_ck_cycle_rejeita_transito_antes_do_fechamento_no_banco(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    lawsuit_id = await factory.create()
    async with factory.sessions() as session:
        with pytest.raises(IntegrityError):
            async with session.begin():
                await set_tenant_context(session, factory.gestor.tenant_id)
                await session.execute(
                    text(
                        "UPDATE lawsuits SET closure_date = '2026-03-10', "
                        "transit_date = '2026-03-01' "
                        "WHERE id = CAST(:id AS uuid)"
                    ),
                    {"id": lawsuit_id},
                )


async def test_ck_cycle_rejeita_arquivamento_antes_do_transito_no_banco(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    lawsuit_id = await factory.create()
    async with factory.sessions() as session:
        with pytest.raises(IntegrityError):
            async with session.begin():
                await set_tenant_context(session, factory.gestor.tenant_id)
                await session.execute(
                    text(
                        "UPDATE lawsuits SET closure_date = '2026-03-01', "
                        "transit_date = '2026-03-10', archived_date = '2026-03-05' "
                        "WHERE id = CAST(:id AS uuid)"
                    ),
                    {"id": lawsuit_id},
                )
