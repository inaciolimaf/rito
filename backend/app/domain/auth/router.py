import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_redis, get_session, get_tenant_id
from app.domain.auth.deps import get_current_user
from app.domain.auth.exceptions import (
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    InvalidResetTokenError,
    RateLimitExceededError,
    WeakPasswordError,
)
from app.domain.auth.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    MeResponse,
    RefreshRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.domain.auth.service import AuthService
from app.domain.users.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> TokenResponse:
    client_ip = request.client.host if request.client else "unknown"
    service = AuthService(session=session, redis=redis, tenant_id=tenant_id)
    try:
        access_token, refresh_token, expires_in = await service.login(
            payload.email, payload.password, client_ip
        )
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=429, detail="Muitas tentativas. Tente novamente em instantes."
        ) from exc
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos.") from exc
    return TokenResponse(
        access_token=access_token, refresh_token=refresh_token, expires_in=expires_in
    )


@router.post("/refresh")
async def refresh(
    payload: RefreshRequest,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> TokenResponse:
    service = AuthService(session=session, redis=redis, tenant_id=tenant_id)
    try:
        access_token, refresh_token, expires_in = await service.refresh(payload.refresh_token)
    except InvalidRefreshTokenError as exc:
        raise HTTPException(status_code=401, detail="Refresh token inválido.") from exc
    return TokenResponse(
        access_token=access_token, refresh_token=refresh_token, expires_in=expires_in
    )


@router.post("/logout", status_code=204)
async def logout(
    payload: LogoutRequest,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> None:
    service = AuthService(session=session, redis=redis, tenant_id=tenant_id)
    await service.logout(payload.refresh_token)


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        id=current_user.id,
        name=current_user.name,
        email=str(current_user.email),
        tenant=current_user.tenant_id,
    )


@router.post("/forgot-password", status_code=202)
async def forgot_password(
    payload: ForgotPasswordRequest,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> None:
    service = AuthService(session=session, redis=redis, tenant_id=tenant_id)
    await service.forgot_password(payload.email)


@router.post("/reset-password", status_code=204)
async def reset_password(
    payload: ResetPasswordRequest,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> None:
    service = AuthService(session=session, redis=redis, tenant_id=tenant_id)
    try:
        await service.reset_password(payload.token, payload.password)
    except WeakPasswordError as exc:
        raise HTTPException(
            status_code=422, detail={"detail": "Senha não atende à política.", "errors": exc.errors}
        ) from exc
    except InvalidResetTokenError as exc:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado.") from exc
