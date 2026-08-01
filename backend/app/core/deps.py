from collections.abc import AsyncGenerator
from typing import cast
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rls import set_tenant_context
from app.integrations.storage.base import FileStorage


async def get_tenant_id(x_tenant_id: str | None = Header(default=None)) -> UUID:
    """Resolve o tenant pelo header X-Tenant-Id.

    Usado só pelos endpoints de autenticação (login, refresh, forgot/reset-password)
    — antes de existir um JWT não há outra forma de saber o tenant. Toda rota
    autenticada usa `get_current_user` (app/domain/auth/deps.py), que tira o
    tenant do claim do token em vez do header (spec 004, regra 8).
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


async def get_redis(request: Request) -> Redis:
    return cast(Redis, request.app.state.redis)


async def get_file_storage(request: Request) -> FileStorage:
    return cast(FileStorage, request.app.state.file_storage)
