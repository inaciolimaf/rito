import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.models import Tenant
from app.core.rls import enable_rls_statements, set_tenant_context
from app.core.security import hash_password
from app.core.tokens import create_access_token
from app.domain.users.models import FinancialAccess, User, UserRole
from tests.conftest import use_test_session

# admin_engine / app_session_factory viraram fixtures compartilhadas em tests/conftest.py
# (spec 009) — tests/meta/ também precisa delas e um conftest de subpasta não é visível
# para pastas irmãs.


@pytest.fixture
async def tenant_probe_table(admin_engine: AsyncEngine, worker_id: str) -> AsyncGenerator[str]:
    """Tabela de exemplo só para os testes de isolamento (spec 003, seção 4).

    O nome carrega o `worker_id` do pytest-xdist (`-n auto` roda vários processos
    contra o mesmo `rito_test`) E um sufixo aleatório — o worker_id sozinho não é
    garantia suficiente: sob carga concorrente pesada (`make test` com e2e/frontend
    rodando ao mesmo tempo, spec 006 descoberta), o nome só por worker ainda colidia
    entre execuções/latências diferentes. Um sufixo uuid4 elimina a colisão de vez.
    """
    table_name = f"tenant_probe_{worker_id}_{uuid.uuid4().hex[:8]}"
    # Spec 105: o `DROP` no teardown deixou de existir. A transação do teste ainda está
    # aberta quando as fixtures são finalizadas (é ela que dá o `ROLLBACK`), e ela
    # segura `AccessShareLock` na tabela de sonda que o teste acabou de ler — o `DROP`
    # numa conexão de admin esperava por esse lock para sempre, e a suíte não terminava.
    # Quem limpa agora é o banco do worker, recriado a partir do template a cada sessão
    # de pytest: mais forte que o `DROP`, porque também leva o que um teste que quebrou
    # no meio tenha deixado.
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


@dataclass
class SeededUser:
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    password: str
    role: UserRole
    financial_access: FinancialAccess


def auth_header(seeded: SeededUser) -> dict[str, str]:
    """Refatoração 070 (regra dos 3 uses): 26 arquivos de teste redefiniam a mesma
    função `_auth_header` local — migrados aqui os de 062-067; os anteriores ficam
    como estão (fora do escopo desta spec, que audita as 9 anteriores)."""
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def make_user(
    app_session_factory: async_sessionmaker[AsyncSession],
) -> Callable[..., Awaitable[SeededUser]]:
    """Cria tenant (se novo) + usuário direto no banco — atalho de teste mais rápido que o
    fluxo real de convite/aceite (spec 012) para cenários que só precisam de um usuário
    pronto, não de testar o próprio fluxo de convite."""

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
async def rbac_client(
    app_engine: AsyncEngine, app_session_factory: async_sessionmaker[AsyncSession]
) -> AsyncGenerator[AsyncClient]:
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

    # Spec 105, regra 5: app descartável, mesma sessão do teste — senão o usuário criado
    # pelo `make_user` (que agora não comita) não existe para este app.
    async with (
        test_app.router.lifespan_context(test_app),
        use_test_session(test_app, app_engine, app_session_factory),
    ):
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
