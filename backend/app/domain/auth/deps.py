import uuid
from collections.abc import AsyncGenerator
from typing import cast

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rls import set_tenant_context
from app.core.tokens import decode_access_token
from app.domain.users.models import User

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> User:
    """Autentica pelo access token — tenant vem do claim, não do header (spec 004, regra 8)."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Não autenticado.")

    try:
        payload = decode_access_token(credentials.credentials)
        tenant_id = uuid.UUID(payload["tenant_id"])
        user_id = uuid.UUID(payload["sub"])
    except (PyJWTError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado.") from exc

    session_factory = request.app.state.session_factory
    async with session_factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        user = await session.get(User, user_id)
        if user is None or not user.is_active:
            raise HTTPException(status_code=401, detail="Usuário não encontrado ou inativo.")
        return cast(User, user)


async def get_session_for_current_user(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> AsyncGenerator[AsyncSession]:
    """Sessão para rotas de domínio autenticadas — tenant vem do usuário logado, não de
    header (spec 004, regra 8). `get_current_user` já abre e fecha sua própria sessão só
    para validar o token; esta é uma sessão nova, que fica aberta durante a rota inteira e
    commita no fim (mesmo padrão de `core.deps.get_session`, que os endpoints de auth
    pré-login usam)."""
    session_factory = request.app.state.session_factory
    async with session_factory() as session, session.begin():
        await set_tenant_context(session, current_user.tenant_id)
        yield session
