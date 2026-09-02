import uuid
from collections.abc import AsyncGenerator
from typing import cast

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock
from app.core.observability.context import tenant_id_var, user_id_var
from app.core.rls import set_tenant_context
from app.core.tokens import decode_access_token
from app.domain.account.models import Account
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
        # Spec 114: o fuso do escritório vem de carona nesta query, não numa segunda.
        # `accounts` é 1:1 com o tenant, então o JOIN não multiplica linha; e o orçamento
        # de queries do §11 não tem folga nenhuma em `/customers/stats` (5 de 5) nem na
        # listagem de contatos (3 de 3) para uma consulta a mais. `outerjoin` porque a
        # conta pode ainda não existir no instante do primeiro login de um tenant novo —
        # aí o fuso é None e o `Clock` cai em DEFAULT_TIMEZONE.
        linha = (
            await session.execute(
                select(User, Account.timezone)
                .outerjoin(Account, Account.tenant_id == User.tenant_id)
                .where(User.id == user_id)
            )
        ).first()
        user = linha[0] if linha is not None else None
        if user is None or not user.is_active:
            raise HTTPException(status_code=401, detail="Usuário não encontrado ou inativo.")
        # Guardado no request e não num ContextVar: é dado da requisição, e `get_clock`
        # o lê pela mesma porta por onde o FastAPI já passa tudo o mais.
        request.state.tenant_timezone = linha[1]
        # Spec 097, regra 1: daqui para a frente todo log da requisição sai com tenant e
        # usuário. Este é o primeiro instante em que eles são conhecidos — o middleware
        # roda antes do token ser validado e não teria como saber.
        tenant_id_var.set(str(tenant_id))
        user_id_var.set(str(user_id))
        return cast(User, user)


async def get_clock(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> Clock:
    """O relógio do escritório logado (spec 114, regras 3 e 5).

    Depende de `get_current_user` por ordem, não por dado: é ele quem resolve o fuso, e o
    FastAPI resolve a dependência uma vez por requisição — então isto não custa query
    nenhuma. Service que precisa saber que dia é hoje recebe isto por `Depends`; nenhum
    deles importa `date` para descobrir sozinho (regra 5, DIP do §5).
    """
    return Clock(getattr(request.state, "tenant_timezone", None))


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
