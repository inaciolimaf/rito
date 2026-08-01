from collections.abc import AsyncGenerator
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rls import set_tenant_context


async def get_tenant_id(x_tenant_id: str | None = Header(default=None)) -> UUID:
    """Resolve o tenant pelo header X-Tenant-Id.

    Provisório: a partir da 004 o tenant passa a vir do JWT.
    """
    if x_tenant_id is None:
        raise HTTPException(status_code=400, detail="Cabeçalho X-Tenant-Id é obrigatório.")
    try:
        return UUID(x_tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="X-Tenant-Id inválido.") from exc


async def get_session(
    request: Request,
    tenant_id: UUID = Depends(get_tenant_id),
) -> AsyncGenerator[AsyncSession]:
    """Sessão com o contexto de tenant já setado (RLS) para a transação inteira.

    Nenhum módulo de domínio cria engine ou sessão própria (CLAUDE.md §5).
    """
    session_factory = request.app.state.session_factory
    async with session_factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        yield session
