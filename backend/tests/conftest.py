import os
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient


def pytest_configure(config: pytest.Config) -> None:
    os.environ.setdefault("APP_ENV", "test")
    os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
    os.environ.setdefault(
        "DATABASE_URL",
        os.environ.get(
            "TEST_DATABASE_URL", "postgresql+asyncpg://rito_app:rito_app@localhost:5432/rito_test"
        ),
    )
    os.environ.setdefault(
        "MIGRATIONS_DATABASE_URL",
        os.environ.get(
            "TEST_MIGRATIONS_DATABASE_URL",
            "postgresql+asyncpg://rito:rito@localhost:5432/rito_test",
        ),
    )
    os.environ.setdefault(
        "REDIS_URL", os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")
    )


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    from app.main import app

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
