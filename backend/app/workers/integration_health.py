"""Job de saúde diário das integrações (spec 049, regra 5) + checagem por
tenant da taxa de vínculo automático (regra 8). Duas fases: a checagem de
saúde é GLOBAL (DJEN/DataJud não são de nenhum tenant — mesma sessão do
superusuário usada pra listar tenants nos outros workers); a taxa de vínculo é
POR TENANT (publicações têm RLS).

Nenhum teste importa este módulo (mesmo padrão de `djen_sync.py`/
`datajud_sync.py`): as regras ficam em `IntegrationHealthService`/
`PublicationMetricsService`, exercitadas direto com fakes.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.bootstrap import migrations_url
from app.core.clock import Clock
from app.core.config import Settings, get_settings
from app.core.db import create_engine_from_url, create_session_factory
from app.core.models import Tenant
from app.core.redis import create_redis_client
from app.core.rls import set_tenant_context
from app.domain.account.repository import AccountRepository
from app.domain.integrations.service import IntegrationHealthChecker, IntegrationHealthService
from app.domain.monitored_terms.repository import TermSyncRunRepository
from app.domain.monitored_terms.schemas import SYNC_RUN_RETENTION_DAYS
from app.domain.publications.metrics import PublicationMetricsService
from app.integrations.datajud.client import DatajudClient
from app.integrations.datajud.health import DatajudHealthChecker
from app.integrations.djen import DjenClient
from app.integrations.djen.health import DjenHealthChecker
from app.integrations.http.audit import DbAuditSink, SafeAuditSink
from app.integrations.http.client import ResilientHttpClient, create_http_client
from app.integrations.http.types import HostPolicy
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

_DJEN_HOST = "comunicaapi.pje.jus.br"
_DATAJUD_HOST = "api-publica.datajud.cnj.jus.br"


async def _check_tenant(
    session_factory: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID, cutoff: datetime
) -> int:
    """Alerta de taxa de vínculo e expurgo de execuções, para um escritório.

    Extraído de `run_daily_check` na spec 114: o corpo do laço cresceu ao resolver o fuso
    por tenant, e a catraca de tamanho de task da spec 117 (regra 5) só desce — subir o
    baseline seria afrouxar o gate em vez de pagar o que ele cobra.
    """
    async with session_factory() as session:
        await set_tenant_context(session, tenant_id)
        # Spec 114, regra 3: o dia é o do tenant. O alerta compara uma janela de dias e
        # sairia deslocado para todo escritório fora do fuso do servidor.
        hoje = Clock(await AccountRepository(session).timezone()).today()
        alert = await PublicationMetricsService(session, tenant_id).check_auto_link_rate(today=hoje)
        await TermSyncRunRepository(session).purge_older_than(cutoff)  # regra 9
        await session.commit()
        return 1 if alert is not None else 0


def _health_http_client(
    settings: Settings, redis: Redis, session_factory: async_sessionmaker[AsyncSession]
) -> ResilientHttpClient:
    """Cliente com a política de rate limit dos DOIS hosts que a sondagem toca.

    A sondagem de saúde bate no DJEN e no DataJud, e passa pelo mesmo token bucket das
    varreduras de verdade (spec 041, regra 4) — de propósito: um health check que fure o
    limite gastaria a cota de quem está trabalhando.
    """
    return create_http_client(
        redis=redis,
        audit=SafeAuditSink(DbAuditSink(session_factory)),
        policies={
            _DJEN_HOST: HostPolicy(rate_limit_per_minute=settings.djen_rate_limit_per_minute),
            _DATAJUD_HOST: HostPolicy(rate_limit_per_minute=settings.datajud_rate_limit_per_minute),
        },
    )


def _health_checkers(
    settings: Settings, http: ResilientHttpClient
) -> list[IntegrationHealthChecker]:
    """As integrações externas que respondem por si mesmas.

    Lista e não registro global: quem entra aqui precisa de credencial e URL montadas com as
    `Settings` do processo, e um registro por import esconderia que a checagem faz chamada de
    rede de verdade. Os dois clientes compartilham o MESMO `http`, que é o que aplica o rate
    limit por host da spec 041 — cada um com o seu furaria o limite.
    """
    return [
        DjenHealthChecker(
            DjenClient(
                http=http, base_url=settings.djen_base_url, user_agent=settings.djen_user_agent
            )
        ),
        DatajudHealthChecker(
            DatajudClient(
                http=http,
                base_url=settings.datajud_base_url,
                api_key=settings.datajud_api_key or "",
            )
        ),
    ]


async def run_daily_check() -> dict[str, int]:
    settings = get_settings()
    url = migrations_url("a varredura cross-tenant de saúde das integrações")
    engine = create_engine_from_url(url)
    session_factory = create_session_factory(engine)
    redis = create_redis_client()
    http = _health_http_client(settings, redis, session_factory)
    try:
        checkers = _health_checkers(settings, http)
        async with session_factory() as session:
            health_service = IntegrationHealthService(session)
            for checker in checkers:
                await health_service.run_check(checker)
            await session.commit()
            tenant_ids = list(
                (await session.scalars(select(Tenant.id).where(Tenant.is_active.is_(True)))).all()
            )

        cutoff = datetime.now(UTC) - timedelta(days=SYNC_RUN_RETENTION_DAYS)
        alerts = sum(
            [await _check_tenant(session_factory, tenant_id, cutoff) for tenant_id in tenant_ids]
        )
        return {"integrations": len(checkers), "tenants": len(tenant_ids), "alerts": alerts}
    finally:
        await http.aclose()
        await redis.aclose()
        await engine.dispose()


@celery_app.task(name="app.workers.integration_health.run_daily_health_check")
def run_daily_health_check() -> dict[str, int]:
    return asyncio.run(run_daily_check())
