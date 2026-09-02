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
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.bootstrap import migrations_url
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


async def _sync_each_tenant(
    tenant_ids: list[uuid.UUID],
    session_factory: async_sessionmaker[AsyncSession],
    client: DatajudClient,
) -> tuple[int, int]:
    """Sincroniza tenant por tenant e devolve `(sincronizados, erros)`.

    Sessão PRÓPRIA por tenant, com `commit` ao fim de cada um: `app.tenant_id` do RLS vive na
    sessão, e reaproveitá-la faria o segundo tenant enxergar o contexto do primeiro. O commit
    por tenant também garante que uma falha lá na frente não desfaça o que já sincronizou.
    """
    settings = get_settings()
    synced = errors = 0
    for tenant_id in tenant_ids:
        async with session_factory() as session:
            await set_tenant_context(session, tenant_id)
            sync_service = MovementSyncService(session, tenant_id, DatajudService(session, client))
            results = await sync_service.sync_due(batch_size=settings.datajud_sync_batch_size)
            await session.commit()
            for result in results:
                if result.status == "error":
                    errors += 1
                else:
                    synced += 1
    return synced, errors


async def run_scheduled_sync() -> dict[str, int]:
    settings = get_settings()
    url = migrations_url("a varredura cross-tenant do DataJud")
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

        synced, errors = await _sync_each_tenant(tenant_ids, session_factory, client)
        return {"tenants": len(tenant_ids), "synced": synced, "errors": errors}
    finally:
        await http.aclose()
        await redis.aclose()
        await engine.dispose()


@celery_app.task(name="app.workers.datajud_sync.sync_due_movements")
def sync_due_movements() -> dict[str, int]:
    return asyncio.run(run_scheduled_sync())
