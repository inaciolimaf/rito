"""Ciclo de vida dos tokens de API (spec 095).

O token é gerado, mostrado uma vez e nunca mais existe em lugar nenhum em texto — o que
fica é o hash SHA-256. Não é bcrypt/argon2 de propósito: token de API tem 32 bytes de
entropia aleatória, não é senha escolhida por humano, então não há dicionário para
atacar; e a autenticação acontece a cada requisição, onde um hash caro custaria latência
em todas elas.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import BaseRepository
from app.domain.api_tokens.models import ApiRequest, ApiToken
from app.domain.api_tokens.schemas import ApiUsageRow
from app.domain.api_tokens.scopes import is_valid

TOKEN_PREFIX = "rito_"
PREFIX_LENGTH = 8
# Regra 14: dez tokens ativos por escritório. Mais que isso é sinal de token esquecido —
# e token esquecido é credencial viva que ninguém rotaciona.
MAX_ACTIVE_TOKENS = 10


class TooManyTokensError(Exception):
    pass


class UnknownScopeError(Exception):
    def __init__(self, scope: str) -> None:
        super().__init__(scope)
        self.scope = scope


def generate_token() -> tuple[str, str, str]:
    """Devolve (token em claro, hash, prefixo)."""
    bruto = f"{TOKEN_PREFIX}{secrets.token_urlsafe(32)}"
    return bruto, hash_token(bruto), bruto[:PREFIX_LENGTH]


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ApiTokenRepository(BaseRepository[ApiToken]):
    model = ApiToken

    async def list_all(self) -> list[ApiToken]:
        stmt = select(ApiToken).order_by(ApiToken.created_at.desc())
        return list((await self.session.scalars(stmt)).all())

    async def count_active(self, *, now: datetime) -> int:
        stmt = select(ApiToken).where(ApiToken.revoked_at.is_(None))
        ativos = [
            token
            for token in (await self.session.scalars(stmt)).all()
            if token.expires_at is None or token.expires_at > now
        ]
        return len(ativos)


class ApiRequestRepository(BaseRepository[ApiRequest]):
    """Leitura do log de requisições da API pública. A agregação por rota vinha montada
    dentro do router (spec 118, checagem 1) — é query, e query mora aqui."""

    model = ApiRequest

    async def usage_by_route(self, *, since: datetime) -> list[ApiUsageRow]:
        stmt = (
            select(
                ApiRequest.path,
                ApiRequest.method,
                func.count().label("calls"),
                func.count().filter(ApiRequest.status_code >= 400).label("errors"),
                func.avg(ApiRequest.duration_ms).label("avg_ms"),
            )
            .where(ApiRequest.created_at >= since)
            .group_by(ApiRequest.path, ApiRequest.method)
            .order_by(func.count().desc())
        )
        return [
            ApiUsageRow(
                path=row.path,
                method=row.method,
                calls=int(row.calls),
                errors=int(row.errors),
                avg_duration_ms=int(row.avg_ms) if row.avg_ms else None,
            )
            for row in (await self.session.execute(stmt)).all()
        ]


class ApiTokenService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.tokens = ApiTokenRepository(session)
        self.requests = ApiRequestRepository(session)

    async def create(
        self,
        *,
        name: str,
        scopes: list[str],
        allowed_ips: list[str] | None,
        expires_at: datetime | None,
        created_by: uuid.UUID,
    ) -> tuple[ApiToken, str]:
        for scope in scopes:
            if not is_valid(scope):
                raise UnknownScopeError(scope)
        if await self.tokens.count_active(now=datetime.now(UTC)) >= MAX_ACTIVE_TOKENS:
            raise TooManyTokensError(
                f"O escritório já tem {MAX_ACTIVE_TOKENS} tokens ativos. "
                "Revogue um antes de criar outro."
            )
        bruto, digest, prefixo = generate_token()
        token = ApiToken(
            tenant_id=self.tenant_id,
            name=name,
            token_hash=digest,
            prefix=prefixo,
            scopes=scopes,
            allowed_ips=allowed_ips,
            expires_at=expires_at,
            created_by=created_by,
        )
        self.session.add(token)
        await self.session.flush()
        return token, bruto

    async def revoke(self, token: ApiToken) -> ApiToken:
        """Revogar não apaga: o log de requisição aponta para o token, e apagar a linha
        transformaria o histórico em `token_id` nulo — o oposto de auditoria."""
        token.revoked_at = datetime.now(UTC)
        await self.session.flush()
        return token

    async def get_by_id(self, token_id: uuid.UUID) -> ApiToken | None:
        return await self.tokens.get_by_id(token_id)

    async def list_tokens(self) -> list[ApiToken]:
        return await self.tokens.list_all()

    async def usage(self, *, days: int) -> list[ApiUsageRow]:
        """Uso por rota nos últimos `days` dias — a janela é regra, não HTTP."""
        return await self.requests.usage_by_route(since=datetime.now(UTC) - timedelta(days=days))


async def lookup_token(session: AsyncSession, raw: str) -> dict[str, Any] | None:
    """Busca o token pelo hash SEM contexto de tenant.

    É a única consulta do sistema que não pode passar pelo RLS — o tenant é justamente o
    que ela descobre. Por isso ela vive numa função `SECURITY DEFINER` (mesmo padrão da
    079 para leitura entre escritórios), e não numa política afrouxada.
    """
    linha = (
        (
            await session.execute(
                text("SELECT * FROM api_token_lookup(:hash)"), {"hash": hash_token(raw)}
            )
        )
        .mappings()
        .first()
    )
    return dict(linha) if linha is not None else None
