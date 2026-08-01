import os
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient


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


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    from app.main import app

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
