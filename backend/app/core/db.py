from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


def create_engine_from_url(url: str) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True)


def create_engine() -> AsyncEngine:
    return create_engine_from_url(get_settings().database_url)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
