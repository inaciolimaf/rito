import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.db import create_engine_from_url, create_session_factory
from app.core.models import Tenant
from app.core.rls import enable_rls_statements, set_tenant_context
from app.core.security import hash_password
from app.domain.users.models import FinancialAccess, User, UserRole


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


@dataclass
class SeededUser:
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    password: str
    role: UserRole
    financial_access: FinancialAccess


@pytest.fixture
def make_user(
    app_session_factory: async_sessionmaker[AsyncSession],
) -> Callable[..., Awaitable[SeededUser]]:
    """Cria tenant (se novo) + usuário direto no banco — não há endpoint de cadastro (spec 012)."""

    async def _make(
        *,
        tenant_id: uuid.UUID | None = None,
        email: str | None = None,
        password: str = "SenhaForte123!",
        is_active: bool = True,
        role: UserRole = UserRole.COLABORADOR,
        financial_access: FinancialAccess = FinancialAccess.NONE,
    ) -> SeededUser:
        tenant_id = tenant_id or uuid.uuid4()
        email = email or f"{uuid.uuid4()}@example.com"

        async with app_session_factory() as session, session.begin():
            existing_tenant = await session.get(Tenant, tenant_id)
            if existing_tenant is None:
                session.add(
                    Tenant(id=tenant_id, slug=f"tenant-{tenant_id}", name="Tenant de teste")
                )

        user_id = uuid.uuid4()
        async with app_session_factory() as session, session.begin():
            await set_tenant_context(session, tenant_id)
            session.add(
                User(
                    id=user_id,
                    tenant_id=tenant_id,
                    email=email,
                    password_hash=hash_password(password),
                    name="Usuário de Teste",
                    is_active=is_active,
                    role=role,
                    financial_access=financial_access,
                )
            )

        return SeededUser(
            tenant_id=tenant_id,
            user_id=user_id,
            email=email,
            password=password,
            role=role,
            financial_access=financial_access,
        )

    return _make


@pytest.fixture
async def rbac_client() -> AsyncGenerator[AsyncClient]:
    """App FastAPI separado só com rotas de exemplo para exercitar require_role/require_financial.

    Não há endpoint de domínio protegido ainda (as specs de negócio começam na 011) — este é
    o mesmo padrão de app descartável usado em tests/integration/test_errors.py.
    """
    from fastapi import APIRouter, Depends

    from app.core.permissions import FinancialAccess, UserRole, require_financial, require_role
    from app.main import create_app

    test_app = create_app()
    router = APIRouter()

    @router.get("/rbac-test/gestor-only", dependencies=[Depends(require_role(UserRole.GESTOR))])
    async def gestor_only() -> dict[str, bool]:
        return {"ok": True}

    @router.get(
        "/rbac-test/administrador-or-above",
        dependencies=[Depends(require_role(UserRole.ADMINISTRADOR))],
    )
    async def administrador_or_above() -> dict[str, bool]:
        return {"ok": True}

    @router.get(
        "/rbac-test/financial-read",
        dependencies=[Depends(require_financial(FinancialAccess.READ_ONLY))],
    )
    async def financial_read() -> dict[str, bool]:
        return {"ok": True}

    @router.post(
        "/rbac-test/financial-write",
        dependencies=[Depends(require_financial(FinancialAccess.FULL))],
    )
    async def financial_write() -> dict[str, bool]:
        return {"ok": True}

    test_app.include_router(router, prefix="/api/v1")

    async with test_app.router.lifespan_context(test_app):
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
