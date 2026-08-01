import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import op


def enable_rls_statements(table_name: str) -> list[str]:
    """SQL para ligar RLS com isolamento por tenant numa tabela de domínio.

    Reutilizado por toda migration que cria uma tabela de domínio a partir da 003.
    """
    return [
        f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY',
        f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY',
        (
            f'CREATE POLICY tenant_isolation ON "{table_name}" '
            "USING (tenant_id = current_setting('app.tenant_id', true)::uuid) "
            "WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid)"
        ),
        f'CREATE INDEX ix_{table_name}_tenant ON "{table_name}" (tenant_id)',
    ]


def enable_rls(table_name: str) -> None:
    """Chamar dentro de upgrade() de uma migration do Alembic."""
    for statement in enable_rls_statements(table_name):
        op.execute(statement)


async def set_tenant_context(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """SET LOCAL app.tenant_id para a transação corrente da sessão.

    Usa `set_config(..., is_local=true)` em vez de `SET LOCAL` porque asyncpg não
    aceita parâmetros ligados (bind params) dentro de comandos SET — `set_config`
    é uma função regular e aceita `$1` normalmente, evitando concatenar o UUID na SQL.
    """
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )
