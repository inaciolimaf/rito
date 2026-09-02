"""Gestão de tokens de API (spec 095 §6) — rotas INTERNAS, com JWT.

Quem cria token é gente logada na UI, não o próprio integrador: um endpoint público que
emitisse tokens seria uma escada para escalar privilégio a partir de um token vazado.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import UserRole, require_role
from app.domain.api_tokens.models import ApiToken
from app.domain.api_tokens.schemas import (
    ApiTokenCreateRequest,
    ApiTokenListResponse,
    ApiTokenResponse,
    ApiUsageResponse,
    ScopeResponse,
)
from app.domain.api_tokens.scopes import ALL_SCOPES, describe
from app.domain.api_tokens.service import (
    ApiTokenService,
    TooManyTokensError,
    UnknownScopeError,
)
from app.domain.auth.deps import get_session_for_current_user
from app.domain.users.models import User

router = APIRouter(prefix="/api-tokens", tags=["api-tokens"])

_NOT_FOUND = "Token não encontrado."


def _to_response(token: ApiToken, *, secret: str | None = None) -> ApiTokenResponse:
    agora = datetime.now(UTC)
    return ApiTokenResponse(
        id=token.id,
        name=token.name,
        prefix=token.prefix,
        scopes=list(token.scopes or []),
        allowed_ips=[str(item) for item in (token.allowed_ips or [])],
        last_used_at=token.last_used_at,
        expires_at=token.expires_at,
        revoked_at=token.revoked_at,
        is_active=(
            token.revoked_at is None and (token.expires_at is None or token.expires_at > agora)
        ),
        created_at=token.created_at,
        token=secret,
    )


@router.get("/scopes")
async def list_scopes(
    _current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
) -> list[ScopeResponse]:
    return [ScopeResponse(scope=scope, description=describe(scope)) for scope in ALL_SCOPES]


@router.get("")
async def list_tokens(
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> ApiTokenListResponse:
    service = ApiTokenService(session, current_user.tenant_id)
    tokens = await service.list_tokens()
    # Sem `token`: o segredo existiu uma vez, na criação (regra 1).
    return ApiTokenListResponse(items=[_to_response(token) for token in tokens], total=len(tokens))


@router.post("", status_code=201)
async def create_token(
    payload: ApiTokenCreateRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> ApiTokenResponse:
    service = ApiTokenService(session, current_user.tenant_id)
    try:
        token, bruto = await service.create(
            name=payload.name,
            scopes=payload.scopes,
            allowed_ips=payload.allowed_ips or None,
            expires_at=payload.expires_at,
            created_by=current_user.id,
        )
    except UnknownScopeError as exc:
        raise HTTPException(status_code=422, detail=f"Escopo desconhecido: {exc.scope}.") from exc
    except TooManyTokensError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_response(token, secret=bruto)


@router.post("/{token_id}/revoke")
async def revoke_token(
    token_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> ApiTokenResponse:
    service = ApiTokenService(session, current_user.tenant_id)
    token = await service.get_by_id(token_id)
    if token is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return _to_response(await service.revoke(token))


@router.get("/usage")
async def get_usage(
    days: int = Query(default=7, ge=1, le=30),
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> ApiUsageResponse:
    """Uso por rota — é a tela que responde "quem está batendo no limite?"."""
    service = ApiTokenService(session, current_user.tenant_id)
    linhas = await service.usage(days=days)
    return ApiUsageResponse(items=linhas, total_calls=sum(row.calls for row in linhas))
