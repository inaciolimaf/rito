"""Healthcheck e exposição de métricas (spec 097, regras 6, 7 e 8).

São dois endpoints com propósitos opostos, e confundi-los é como se derruba um sistema
saudável:

- `/health` é **liveness**. Responde sem tocar em nada (regra 7). Se ele checasse o
  Postgres, uma indisponibilidade de banco faria o orquestrador matar e recriar todos os
  containers da aplicação — que estão perfeitamente vivos — no exato momento em que o
  banco precisa de menos carga, não de mais.
- `/health/ready` é **readiness**. Toca Postgres, Redis e S3, cada um com 2 s de teto
  (regra 8), e diz **qual** falhou. Quem está fora de prontidão sai do balanceador; não
  é morto.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import __version__
from app.core.config import get_settings
from app.core.observability import metrics

router = APIRouter(tags=["health"])
logger = logging.getLogger("rito.health")

# Regra 8. Teto por dependência, não para o conjunto: as três são checadas em paralelo,
# então o pior caso do endpoint inteiro continua sendo 2 s.
PROBE_TIMEOUT_S = 2.0


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


async def _probe(name: str, coro_factory: Callable[[], Awaitable[object]]) -> tuple[str, str]:
    try:
        await asyncio.wait_for(coro_factory(), timeout=PROBE_TIMEOUT_S)
    except TimeoutError:
        logger.warning("sonda de prontidão estourou o tempo", extra={"dependency": name})
        return name, "timeout"
    except Exception:
        logger.warning("sonda de prontidão falhou", extra={"dependency": name})
        return name, "error"
    return name, "ok"


@router.get("/health/ready")
async def health_ready(request: Request) -> JSONResponse:
    async def postgres() -> object:
        async with request.app.state.session_factory() as session:
            return await session.execute(text("SELECT 1"))

    async def redis() -> object:
        return await request.app.state.redis.ping()

    async def storage() -> object:
        return await request.app.state.file_storage.ping()

    resultados = await asyncio.gather(
        _probe("database", postgres),
        _probe("redis", redis),
        _probe("storage", storage),
    )
    corpo = dict(resultados)
    saudavel = all(estado == "ok" for estado in corpo.values())
    return JSONResponse(status_code=200 if saudavel else 503, content=corpo)


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics(
    request: Request, authorization: str | None = Header(default=None)
) -> Response:
    """Regra 6, e "interno" no §5 da spec.

    O `/metrics` conta quantas requisições cada rota recebeu e quanto o escritório
    gastou de LLM — é inventário da operação, não dado público. Com `METRICS_TOKEN`
    configurado ele exige o bearer; sem, fica aberto para o caso em que a rede já
    isola (scrape por rede interna), que é o arranjo mais comum.
    """
    settings = get_settings()
    esperado = settings.metrics_token
    if esperado and authorization != f"Bearer {esperado}":
        raise HTTPException(status_code=401, detail="Métricas exigem token interno.")

    await metrics.observe_queue_depths(request.app.state.redis)
    return Response(content=metrics.render(), media_type=metrics.CONTENT_TYPE)
