"""Sincronização agendada de andamentos via DataJud (spec 047).

Mesmo padrão de `app/workers/djen_sync.py`: `lawsuits` tem FORCE RLS, então a
descoberta de quais tenants têm processo na fila roda como superusuário
(`MIGRATIONS_DATABASE_URL`) — cada tenant sincroniza depois na própria sessão,
com RLS de verdade. Nenhum teste importa este módulo (mesma nota do djen_sync):
as regras moram em `MovementSyncService`/`DatajudService` e são exercitadas
direto, sem fila nem broker.
"""

import asyncio
import logging

from app.core.config import get_settings
from app.core.db import create_engine_from_url, create_session_factory
from app.core.redis import create_redis_client
from app.core.rls import set_tenant_context
from app.domain.datajud.movement_sync_service import MovementSyncService
from app.domain.datajud.service import DatajudService
from app.domain.lawsuits.repository import LawsuitRepository
from app.integrations.datajud.client import DatajudClient
from app.integrations.http.audit import DbAuditSink, SafeAuditSink
from app.integrations.http.client import create_http_client
from app.integrations.http.types import HostPolicy
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

_DATAJUD_HOST = "api-publica.datajud.cnj.jus.br"


async def run_scheduled_sync() -> dict[str, int]:
    settings = get_settings()
    url = settings.migrations_database_url
    assert url is not None, "MIGRATIONS_DATABASE_URL necessária para a varredura cross-tenant"
    engine = create_engine_from_url(url)
    session_factory = create_session_factory(engine)
    redis = create_redis_client()
    http = create_http_client(
        redis=redis,
        audit=SafeAuditSink(DbAuditSink(session_factory)),
        # Regra 9: rate limit do DataJud mora na camada 041, por host, global entre
        # workers.
        policies={
            _DATAJUD_HOST: HostPolicy(rate_limit_per_minute=settings.datajud_rate_limit_per_minute)
        },
    )
    try:
        client = DatajudClient(
            http=http, base_url=settings.datajud_base_url, api_key=settings.datajud_api_key or ""
        )

        async with session_factory() as session:
            tenant_ids = list(await LawsuitRepository(session).list_due_tenant_ids())

        synced = errors = 0
        for tenant_id in tenant_ids:
            async with session_factory() as session:
                await set_tenant_context(session, tenant_id)
                datajud_service = DatajudService(session, client)
                sync_service = MovementSyncService(session, tenant_id, datajud_service)
                results = await sync_service.sync_due(batch_size=settings.datajud_sync_batch_size)
                await session.commit()
                for result in results:
                    if result.status == "error":
                        errors += 1
                    else:
                        synced += 1
        return {"tenants": len(tenant_ids), "synced": synced, "errors": errors}
    finally:
        await http.aclose()
        await redis.aclose()
        await engine.dispose()


@celery_app.task(name="app.workers.datajud_sync.sync_due_movements")  # type: ignore[untyped-decorator]
def sync_due_movements() -> dict[str, int]:
    return asyncio.run(run_scheduled_sync())
