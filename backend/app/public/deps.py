"""Autenticação, escopo e limite da API pública (spec 095).

Tudo que a API pública tem de diferente da interna mora aqui: o tenant vem do TOKEN (e
não de um JWT de usuário), o limite é por token, e cada requisição vira uma linha de log.

O que **não** muda: a mesma sessão com `app.tenant_id` setado, o mesmo RLS, os mesmos
services. Um caminho de leitura paralelo — "mais rápido porque pula o RLS" — seria a
forma mais fácil de vazar dado entre escritórios, e por isso ele não existe.

Spec 134: e as mesmas PERMISSÕES. O token não é um sujeito próprio — ele age em nome de
quem o emitiu, e por isso o dono é lido a cada requisição: quem foi desativado às 18h não
escreve às 19h, e quem perdeu o acesso financeiro perde junto o `write:transactions` que
já tinha em mãos. Permissão avaliada no momento do ato, não no da emissão.
"""

import ipaddress
import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

from fastapi import Depends, Header, HTTPException, Request
from redis.asyncio import Redis
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_redis
from app.core.invariants import not_none
from app.core.permissions import capabilities_for
from app.core.rate_limit import check_and_increment
from app.core.rls import set_tenant_context
from app.domain.api_tokens.models import ApiRequest, ApiToken
from app.domain.api_tokens.scopes import describe, required_capability
from app.domain.api_tokens.service import lookup_token
from app.domain.users.models import User

logger = logging.getLogger("rito.public_api")

# Regra 5. Os três limites da spec, e a janela de cada um.
GET_LIMIT_PER_MINUTE = 30
POST_LIMIT_PER_DAY = 500
PUT_LIMIT_PER_DAY = 500

# Regra 8.
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 1000

# Spec 134, regra 5. Tentativa de autenticação que FALHA, contada por origem: é o
# contador que existe justamente onde o outro não pode existir — o de rota é por token, e
# quem está adivinhando token ainda não tem um. Vinte por minuto não atrapalha ninguém que
# erra a configuração e mata a varredura, que precisa de milhares.
FAILED_AUTH_LIMIT_PER_MINUTE = 20
FAILED_AUTH_WINDOW_SECONDS = 60

# Marca a dependência de escopo para o gate de cobertura de permissão
# (`tests/integration/test_permission_coverage.py`), no mesmo idioma do
# `is_permission_dependency` de `app/core/permissions.py`: rota pública nova sem
# `require_scope` reprova o CI em vez de nascer aberta a qualquer token.
_SCOPE_MARKER: Final = "_rito_public_scope"


@dataclass(frozen=True)
class ApiCaller:
    """Quem está chamando: o token, o escritório dele e o que ele pode fazer.

    `capabilities` é a matriz de `app/core/permissions.py` resolvida para o DONO do token
    no instante da requisição (spec 134). Guardar a capacidade, e não o perfil e o acesso
    financeiro separados, é o que faz um eixo de permissão novo valer aqui sem uma segunda
    tabela para manter em dia.
    """

    token_id: uuid.UUID
    tenant_id: uuid.UUID
    scopes: frozenset[str]
    acting_user_id: uuid.UUID
    capabilities: frozenset[str] = frozenset()

    def has(self, scope: str) -> bool:
        return scope in self.scopes

    def can(self, capability: str) -> bool:
        return capability in self.capabilities


def _unauthorized(detail: str) -> HTTPException:
    # `WWW-Authenticate` porque é uma API para máquina: o cliente HTTP precisa do sinal
    # padrão, não só do texto.
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


async def get_api_caller(
    request: Request,
    authorization: str | None = Header(default=None),
    redis: Redis = Depends(get_redis),
) -> ApiCaller:
    """Resolve o token e o DONO dele — nesta ordem, e as duas coisas a cada requisição.

    Ler o usuário custa uma consulta por chamada, e é o preço de a permissão valer no
    momento do ato: sem ela, offboarding não invalida credencial nenhuma e o token
    continua sendo a fotografia do que seu dono podia no dia em que o emitiu.
    """
    await _guard_brute_force(redis, request)
    bruto = _bearer_of(authorization)
    if bruto is None:
        raise await _reject(redis, request, "Envie o token em Authorization: Bearer <token>.")

    linha, dono = await _load_token(request, bruto)
    if linha is None:
        raise await _reject(redis, request, "Token inválido.")
    # Daqui para baixo o token EXISTE: a tentativa é registrável em `api_requests` (regra
    # 9), e é justamente ela — token revogado sendo usado — o sinal de credencial vazada
    # que mais interessa guardar.
    request.state.api_caller = _caller_of(linha, capabilities=frozenset())

    recusa = _rejection_reason(linha, request, dono)
    if recusa is not None:
        raise await _reject(redis, request, recusa)

    dono = not_none(dono, "`_rejection_reason` recusa o token cujo dono não está ativo")
    caller = _caller_of(
        linha, capabilities=frozenset(capabilities_for(dono.role, dono.financial_access))
    )
    request.state.api_caller = caller
    return caller


def _bearer_of(authorization: str | None) -> str | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return authorization.split(" ", 1)[1].strip() or None


async def _load_token(request: Request, bruto: str) -> tuple[dict[str, Any] | None, User | None]:
    """O token e o usuário que o emitiu, na MESMA transação.

    `lookup_token` é a única consulta sem contexto de tenant (é o tenant que ela
    descobre); o dono já vem pelo RLS, com o `app.tenant_id` que ela acabou de revelar.
    """
    session_factory = request.app.state.session_factory
    async with session_factory() as session, session.begin():
        linha = await lookup_token(session, bruto)
        if linha is None:
            return None, None
        await set_tenant_context(session, linha["tenant_id"])
        return linha, await session.get(User, linha["created_by"])


def _rejection_reason(linha: dict[str, Any], request: Request, dono: User | None) -> str | None:
    """Os quatro motivos de recusar um token que existe — todos 401, todos com o texto
    que o integrador precisa para saber o que fazer."""
    if linha["revoked_at"] is not None:
        return "Este token foi revogado."
    if linha["expires_at"] is not None and linha["expires_at"] <= datetime.now(UTC):
        return "Este token expirou."
    permitidos = linha["allowed_ips"]
    # Regra 3: a restrição por IP só faz sentido se o IP recusado NÃO souber que o token
    # é válido — por isso 401, e não 403.
    if permitidos and not _ip_allowed(_client_ip(request), permitidos):
        return "Origem não autorizada para este token."
    # Spec 134, regra 4: o token age em nome de quem o emitiu. Desativado o dono, ele não
    # age mais — o advogado desligado às 18h não cria contato às 19h.
    if dono is None or not dono.is_active:
        return "O usuário dono deste token não está mais ativo."
    return None


def _caller_of(linha: dict[str, Any], *, capabilities: frozenset[str]) -> ApiCaller:
    return ApiCaller(
        token_id=linha["id"],
        tenant_id=linha["tenant_id"],
        scopes=frozenset(linha["scopes"] or []),
        acting_user_id=linha["created_by"],
        capabilities=capabilities,
    )


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _failure_key(request: Request) -> str:
    # Prefixo `api:rl:` de propósito: é o mesmo namespace dos contadores de rota, e quem
    # opera o Redis enxerga os limites da API pública numa varredura só.
    return f"api:rl:auth:{_client_ip(request) or 'desconhecido'}"


async def _failed_attempts(redis: Redis, chave: str) -> int:
    """Lê o contador SEM incrementá-lo — quem chega com token bom não pode ser punido por
    quem errou o dele. O `decode` cobre as duas configurações de cliente Redis do
    projeto (o do app devolve bytes; o dos testes, texto)."""
    bruto = await redis.get(chave)
    if bruto is None:
        return 0
    return int(bruto.decode() if isinstance(bruto, bytes) else bruto)


async def _guard_brute_force(redis: Redis, request: Request) -> None:
    """Regra 5 da 134: falha de autenticação também tem teto.

    Sem ele, adivinhar token é de graça — cada tentativa custa ao Rito uma sessão e uma
    consulta, e nada além do acaso separa a varredura do acerto. O contador é por ORIGEM
    porque é o único identificador que existe antes de haver token, e conta só FALHA:
    o integrador que varre a base com credencial válida nunca chega perto dele.
    """
    chave = _failure_key(request)
    if await _failed_attempts(redis, chave) < FAILED_AUTH_LIMIT_PER_MINUTE:
        return
    espera = max(int(await redis.ttl(chave)), 1)
    raise HTTPException(
        status_code=429,
        detail="Tentativas de autenticação demais desta origem. Tente de novo em instantes.",
        headers={"Retry-After": str(espera)},
    )


async def _reject(redis: Redis, request: Request, detail: str) -> HTTPException:
    """Conta a tentativa falha, registra e devolve o 401 para quem chamou levantar.

    O log é WARNING e leva a origem: uma rajada de 401 é o desenho de um ataque, e sem
    linha nenhuma ela some — a regra 9 promete registrar TODA requisição, e a que falhou
    é a que mais interessa. Quando o token existe, a linha em `api_requests` sai junto,
    pelo middleware.
    """
    await check_and_increment(
        redis,
        _failure_key(request),
        limit=FAILED_AUTH_LIMIT_PER_MINUTE,
        window_seconds=FAILED_AUTH_WINDOW_SECONDS,
    )
    logger.warning(
        "autenticação recusada na API pública",
        extra={"public_api_reason": detail, "public_api_client": _client_ip(request)},
    )
    return _unauthorized(detail)


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
    """Escopo do TOKEN e permissão do DONO dele — as duas, sempre, na mesma dependência.

    Regra 2: o 403 diz QUAL escopo falta — um "acesso negado" seco obrigaria o integrador
    a adivinhar entre sete recursos.

    Spec 134, regra 3: a permissão do dono é conferida aqui, e não em cada rota, porque a
    exigência é derivada do próprio escopo (`required_capability`). Uma rota financeira
    nova não tem como esquecer o gate — ela o herda de pedir `write:transactions`.
    """
    capacidade = required_capability(scope)

    async def dependency(caller: ApiCaller = Depends(get_api_caller)) -> ApiCaller:
        if not caller.has(scope):
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Este token não tem o escopo '{scope}' (permite {describe(scope)}). "
                    "Gere um token novo com o escopo necessário."
                ),
            )
        if capacidade is not None and not caller.can(capacidade):
            raise HTTPException(
                status_code=403,
                detail=(
                    "O usuário dono deste token não tem acesso financeiro suficiente para "
                    f"'{scope}'. O token não amplia o que o dono pode."
                ),
            )
        return caller

    setattr(dependency, _SCOPE_MARKER, scope)
    return dependency


def declared_scope(call: object) -> str | None:
    """Usado pelo gate de cobertura de permissão: devolve o escopo que a rota exige, ou
    `None` se a dependência não é de escopo."""
    marcado = getattr(call, _SCOPE_MARKER, None)
    return marcado if isinstance(marcado, str) else None


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
