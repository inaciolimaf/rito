"""Autenticação, escopo e limite da API pública (spec 095).

Tudo que a API pública tem de diferente da interna mora aqui: o tenant vem do TOKEN (e
não de um JWT de usuário), o limite é por token, e cada requisição vira uma linha de log.

O que **não** muda: a mesma sessão com `app.tenant_id` setado, o mesmo RLS, os mesmos
services. Um caminho de leitura paralelo — "mais rápido porque pula o RLS" — seria a
forma mais fácil de vazar dado entre escritórios, e por isso ele não existe.
"""

import ipaddress
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, Header, HTTPException, Request
from redis.asyncio import Redis
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_redis
from app.core.rls import set_tenant_context
from app.domain.api_tokens.models import ApiRequest, ApiToken
from app.domain.api_tokens.scopes import describe
from app.domain.api_tokens.service import lookup_token

# Regra 5. Os três limites da spec, e a janela de cada um.
GET_LIMIT_PER_MINUTE = 30
POST_LIMIT_PER_DAY = 500
PUT_LIMIT_PER_DAY = 500

# Regra 8.
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 1000


@dataclass(frozen=True)
class ApiCaller:
    """Quem está chamando: o token, o escritório dele e o que ele pode fazer."""

    token_id: uuid.UUID
    tenant_id: uuid.UUID
    scopes: frozenset[str]
    acting_user_id: uuid.UUID

    def has(self, scope: str) -> bool:
        return scope in self.scopes


def _unauthorized(detail: str) -> HTTPException:
    # `WWW-Authenticate` porque é uma API para máquina: o cliente HTTP precisa do sinal
    # padrão, não só do texto.
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


async def get_api_caller(
    request: Request,
    authorization: str | None = Header(default=None),
) -> ApiCaller:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _unauthorized("Envie o token em Authorization: Bearer <token>.")
    bruto = authorization.split(" ", 1)[1].strip()

    session_factory = request.app.state.session_factory
    async with session_factory() as session, session.begin():
        linha = await lookup_token(session, bruto)
    if linha is None:
        raise _unauthorized("Token inválido.")

    agora = datetime.now(UTC)
    if linha["revoked_at"] is not None:
        raise _unauthorized("Este token foi revogado.")
    if linha["expires_at"] is not None and linha["expires_at"] <= agora:
        raise _unauthorized("Este token expirou.")

    permitidos = linha["allowed_ips"]
    # Regra 3: a restrição por IP só faz sentido se o IP recusado NÃO souber que o token
    # é válido — por isso 401, e não 403.
    if permitidos and not _ip_allowed(request.client.host if request.client else None, permitidos):
        raise _unauthorized("Origem não autorizada para este token.")

    caller = ApiCaller(
        token_id=linha["id"],
        tenant_id=linha["tenant_id"],
        scopes=frozenset(linha["scopes"] or []),
        acting_user_id=linha["created_by"],
    )
    request.state.api_caller = caller
    return caller


def _ip_allowed(client_ip: str | None, allowed: list[str]) -> bool:
    if client_ip is None:
        return False
    try:
        endereco = ipaddress.ip_address(client_ip)
    except ValueError:  # pragma: no cover - starlette sempre entrega IP válido
        return False
    for entrada in allowed:
        try:
            if endereco in ipaddress.ip_network(str(entrada), strict=False):
                return True
        except ValueError:  # pragma: no cover - a coluna é INET
            continue
    return False


def require_scope(scope: str) -> Any:
    """Regra 2: o 403 diz QUAL escopo falta — um 'acesso negado' seco obrigaria o
    integrador a adivinhar entre sete recursos."""

    async def dependency(caller: ApiCaller = Depends(get_api_caller)) -> ApiCaller:
        if not caller.has(scope):
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Este token não tem o escopo '{scope}' (permite {describe(scope)}). "
                    "Gere um token novo com o escopo necessário."
                ),
            )
        return caller

    return dependency


async def get_public_session(
    request: Request, caller: ApiCaller = Depends(get_api_caller)
) -> AsyncIterator[AsyncSession]:
    """Regra 6: a sessão da API pública é a MESMA da interna, com `app.tenant_id` vindo
    do token. Nenhum atalho — o RLS continua sendo quem isola."""
    session_factory = request.app.state.session_factory
    async with session_factory() as session, session.begin():
        await set_tenant_context(session, caller.tenant_id)
        yield session


# ------------------------------------------------------------------- limite


def _limit_for(method: str) -> tuple[int, int, str]:
    """(limite, janela em segundos, unidade legível)."""
    if method == "GET":
        return GET_LIMIT_PER_MINUTE, 60, "minuto"
    if method == "POST":
        return POST_LIMIT_PER_DAY, 86_400, "dia"
    return PUT_LIMIT_PER_DAY, 86_400, "dia"


async def enforce_rate_limit(
    request: Request,
    caller: ApiCaller = Depends(get_api_caller),
    redis: Redis = Depends(get_redis),
) -> None:
    """Regra 5: contador por token, por rota e por janela, no Redis.

    A chave inclui a ROTA (`request.scope["route"].path`, não o caminho com ids) porque a
    spec fala em "500 POST/dia por rota": um script que cria clientes não pode consumir a
    cota de quem cria processos.
    """
    limite, janela, unidade = _limit_for(request.method)
    rota = getattr(request.scope.get("route"), "path", request.url.path)
    chave = f"api:rl:{caller.token_id}:{request.method}:{rota}:{int(time.time()) // janela}"

    atual = await redis.incr(chave)
    if atual == 1:
        await redis.expire(chave, janela)
    restante = await redis.ttl(chave)
    reset = max(int(restante), 0)

    request.state.rate_limit = (limite, max(limite - int(atual), 0), reset)
    if int(atual) > limite:
        raise HTTPException(
            status_code=429,
            detail=f"Limite de {limite} requisições por {unidade} atingido nesta rota.",
            headers={
                "Retry-After": str(reset or janela),
                "X-RateLimit-Limit": str(limite),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset or janela),
            },
        )


# --------------------------------------------------------------------- log


async def record_request(request: Request, *, status_code: int, duration_ms: int) -> None:
    """Regra 9. Sessão própria e curta: o log precisa sobreviver ao rollback da
    requisição que falhou — que é justamente a que mais interessa registrar."""
    caller: ApiCaller | None = getattr(request.state, "api_caller", None)
    if caller is None:
        return
    session_factory = request.app.state.session_factory
    async with session_factory() as session, session.begin():
        await set_tenant_context(session, caller.tenant_id)
        # Regra 13: `last_used_at` é atualizado AQUI, depois da resposta ter saído — um
        # UPDATE no caminho crítico faria toda leitura da API custar uma escrita.
        await session.execute(
            update(ApiToken)
            .where(ApiToken.id == caller.token_id)
            .values(last_used_at=datetime.now(UTC))
        )
        session.add(
            ApiRequest(
                tenant_id=caller.tenant_id,
                token_id=caller.token_id,
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_ms=duration_ms,
                ip_address=request.client.host if request.client else None,
            )
        )
