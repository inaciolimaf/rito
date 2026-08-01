import os
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


def pytest_configure(config: pytest.Config) -> None:
    # Força (não só setdefault) — testes NUNCA podem herdar um DATABASE_URL/REDIS_URL de
    # ambiente apontando para um banco que não seja o de teste. Descoberto na spec 006: rodar
    # `make test` com DATABASE_URL exportado no shell (para o webServer do e2e, que aponta pro
    # banco "rito" de dev) fazia o pytest herdar esse valor via setdefault e testar contra o
    # banco errado — sem erro óbvio, só "relation does not exist" nas tabelas criadas só em
    # rito_test. Sempre sobrescrever com TEST_* elimina essa classe de bug inteira.
    os.environ["APP_ENV"] = "test"
    os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
    os.environ["DATABASE_URL"] = os.environ.get(
        "TEST_DATABASE_URL", "postgresql+asyncpg://rito_app:rito_app@localhost:5432/rito_test"
    )
    os.environ["MIGRATIONS_DATABASE_URL"] = os.environ.get(
        "TEST_MIGRATIONS_DATABASE_URL",
        "postgresql+asyncpg://rito:rito@localhost:5432/rito_test",
    )
    os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")
    os.environ["ARGON2_TIME_COST"] = os.environ.get("TEST_ARGON2_TIME_COST", "1")
    os.environ["ARGON2_MEMORY_COST"] = os.environ.get("TEST_ARGON2_MEMORY_COST", "8192")
    # MinIO é infra local (como Postgres/Redis) — testes de logo (spec 011) usam o serviço
    # de verdade do docker-compose, só num bucket separado do de dev, nunca um fake.
    os.environ["S3_ENDPOINT_URL"] = os.environ.get("TEST_S3_ENDPOINT_URL", "http://localhost:9000")
    os.environ["S3_ACCESS_KEY"] = os.environ.get("TEST_S3_ACCESS_KEY", "minioadmin")
    os.environ["S3_SECRET_KEY"] = os.environ.get("TEST_S3_SECRET_KEY", "minioadmin")
    os.environ["S3_BUCKET"] = os.environ.get("TEST_S3_BUCKET", "rito-test")
    os.environ["S3_REGION"] = os.environ.get("TEST_S3_REGION", "us-east-1")


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    from app.main import app

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest.fixture
async def admin_engine() -> AsyncGenerator[AsyncEngine]:
    """Engine com o superusuário (MIGRATIONS_DATABASE_URL) — bypassa RLS, só para setup/
    verificação de teste (DDL, tabelas de sonda, conferir estado de migration)."""
    from app.core.config import get_settings
    from app.core.db import create_engine_from_url

    url = get_settings().migrations_database_url
    assert url is not None, "MIGRATIONS_DATABASE_URL não configurada para os testes"
    engine = create_engine_from_url(url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def app_session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    """Engine com a role de aplicação (rito_app, sem BYPASSRLS) — RLS vale de verdade."""
    from app.core.config import get_settings
    from app.core.db import create_engine_from_url, create_session_factory

    engine = create_engine_from_url(get_settings().database_url)
    yield create_session_factory(engine)
    await engine.dispose()
