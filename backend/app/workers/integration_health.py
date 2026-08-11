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
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import create_engine_from_url, create_session_factory
from app.core.models import Tenant
from app.core.redis import create_redis_client
from app.core.rls import set_tenant_context
from app.domain.integrations.service import IntegrationHealthChecker, IntegrationHealthService
from app.domain.monitored_terms.repository import TermSyncRunRepository
from app.domain.monitored_terms.schemas import SYNC_RUN_RETENTION_DAYS
from app.domain.publications.metrics import PublicationMetricsService
from app.integrations.datajud.client import DatajudClient
from app.integrations.datajud.health import DatajudHealthChecker
from app.integrations.djen import DjenClient
from app.integrations.djen.health import DjenHealthChecker
from app.integrations.http.audit import DbAuditSink, SafeAuditSink
from app.integrations.http.client import create_http_client
from app.integrations.http.types import HostPolicy
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

_DJEN_HOST = "comunicaapi.pje.jus.br"
_DATAJUD_HOST = "api-publica.datajud.cnj.jus.br"


async def run_daily_check() -> dict[str, int]:
    settings = get_settings()
    url = settings.migrations_database_url
    assert url is not None, "MIGRATIONS_DATABASE_URL necessária para a varredura cross-tenant"
    engine = create_engine_from_url(url)
    session_factory = create_session_factory(engine)
    redis = create_redis_client()
    http = create_http_client(
        redis=redis,
        audit=SafeAuditSink(DbAuditSink(session_factory)),
        policies={
            _DJEN_HOST: HostPolicy(rate_limit_per_minute=settings.djen_rate_limit_per_minute),
            _DATAJUD_HOST: HostPolicy(rate_limit_per_minute=settings.datajud_rate_limit_per_minute),
        },
    )
    try:
        checkers: list[IntegrationHealthChecker] = [
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

        async with session_factory() as session:
            health_service = IntegrationHealthService(session)
            for checker in checkers:
                await health_service.run_check(checker)
            await session.commit()
            tenant_ids = list(
                (await session.scalars(select(Tenant.id).where(Tenant.is_active.is_(True)))).all()
            )

        cutoff = datetime.now(UTC) - timedelta(days=SYNC_RUN_RETENTION_DAYS)
        alerts = 0
        for tenant_id in tenant_ids:
            async with session_factory() as session:
                await set_tenant_context(session, tenant_id)
                alert = await PublicationMetricsService(session, tenant_id).check_auto_link_rate()
                await TermSyncRunRepository(session).purge_older_than(cutoff)  # regra 9
                await session.commit()
                if alert is not None:
                    alerts += 1
        return {"integrations": len(checkers), "tenants": len(tenant_ids), "alerts": alerts}
    finally:
        await http.aclose()
        await redis.aclose()
        await engine.dispose()


@celery_app.task(name="app.workers.integration_health.run_daily_health_check")  # type: ignore[untyped-decorator]
def run_daily_health_check() -> dict[str, int]:
    return asyncio.run(run_daily_check())
