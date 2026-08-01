from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.db import create_engine_from_url, create_session_factory
from app.core.rls import enable_rls_statements


@pytest.fixture
async def admin_engine() -> AsyncGenerator[AsyncEngine]:
    url = get_settings().migrations_database_url
    assert url is not None, "MIGRATIONS_DATABASE_URL não configurada para os testes"
    engine = create_engine_from_url(url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def app_session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    engine = create_engine_from_url(get_settings().database_url)
    yield create_session_factory(engine)
    await engine.dispose()


@pytest.fixture
async def tenant_probe_table(admin_engine: AsyncEngine, worker_id: str) -> AsyncGenerator[str]:
    """Tabela de exemplo só para os testes de isolamento (spec 003, seção 4).

    O nome carrega o `worker_id` do pytest-xdist porque `-n auto` roda os testes
    deste arquivo em processos concorrentes contra o mesmo `rito_test` — sem
    isso, dois workers criando/derrubando a mesma tabela colidem.
    """
    table_name = f"tenant_probe_{worker_id}"
    ddl = (
        f"CREATE TABLE IF NOT EXISTS {table_name} ("
        "id UUID PRIMARY KEY DEFAULT uuid_generate_v4(), "
        "tenant_id UUID NOT NULL, "
        "label TEXT NOT NULL"
        ")"
    )
    async with admin_engine.begin() as conn:
        await conn.execute(text(ddl))
        for statement in enable_rls_statements(table_name):
            await conn.execute(text(statement))
        await conn.execute(
            text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table_name} TO rito_app")
        )

    yield table_name

    async with admin_engine.begin() as conn:
        await conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
