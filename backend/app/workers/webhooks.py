"""Retentativa e retenção de webhooks (spec 093, regras 3 e 12).

O backoff é de 1, 5 e 15 minutos — segurar a request do usuário por 21 minutos seria
absurdo, então quem volta é este worker. Mesmo padrão dos outros: por tenant, e uma falha
num tenant não trava os demais.

Nenhum teste importa este módulo: a regra mora em `WebhookService.retry_due` e é
exercitada direto, sem fila (CLAUDE.md §3).
"""

import asyncio
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import create_engine, create_session_factory
from app.core.models import Tenant
from app.core.rls import set_tenant_context
from app.domain.webhooks.sender import HttpxWebhookSender
from app.domain.webhooks.service import WebhookService
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _for_tenant(
    session_factory: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID
) -> int:
    async with session_factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        service = WebhookService(session, tenant_id, sender=HttpxWebhookSender())
        retentadas = await service.retry_due()
        await service.purge_old()
        return retentadas


async def _sweep() -> int:
    engine = create_engine()
    session_factory = create_session_factory(engine)
    total = 0
    try:
        async with session_factory() as session:
            tenant_ids = (
                await session.scalars(select(Tenant.id).where(Tenant.is_active.is_(True)))
            ).all()
        for tenant_id in tenant_ids:
            try:
                total += await _for_tenant(session_factory, tenant_id)
            except Exception:  # um tenant com problema não trava os demais
                logger.exception("webhooks: falha inesperada no tenant %s", tenant_id)
    finally:
        await engine.dispose()
    return total


@celery_app.task(name="app.workers.webhooks.sweep_webhook_deliveries")  # type: ignore[untyped-decorator]
def sweep_webhook_deliveries() -> int:
    return asyncio.run(_sweep())
