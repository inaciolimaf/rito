"""Régua de cobrança diária (spec 061, regra 10) — job diário que varre os tenants
ativos e dispara `DunningService.run_daily_rules` pra cada um. Mesmo padrão de
`app/workers/stagnation.py` (spec 052): uma falha por tenant não derruba os demais, e
dentro de cada tenant uma falha por lançamento não derruba os demais (regra 10, dentro
do próprio `DunningService.run_daily_rules`).

Nenhum teste importa este módulo — a regra em si mora em `DunningService` e é
exercitada direto, sem fila (CLAUDE.md §3)."""

import asyncio
import logging
import uuid
from datetime import date

from sqlalchemy import select

from app.core.db import create_engine, create_session_factory
from app.core.models import Tenant
from app.core.rls import set_tenant_context
from app.domain.dunning.service import DunningService
from app.integrations.messaging.registry import create_messaging_channels
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _run_for_tenant(tenant_id: uuid.UUID, reference_date: date) -> int:
    engine = create_engine()
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session, session.begin():
            await set_tenant_context(session, tenant_id)
            service = DunningService(
                session=session, tenant_id=tenant_id, channels=create_messaging_channels()
            )
            return await service.run_daily_rules(reference_date)
    finally:
        await engine.dispose()


async def _sweep_all_tenants(reference_date: date) -> int:
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
                total += await _run_for_tenant(tenant_id, reference_date)
            except Exception:  # um tenant com problema não pode travar os demais
                logger.exception("dunning: falha inesperada no tenant %s", tenant_id)
    finally:
        await engine.dispose()
    return total


@celery_app.task(name="app.workers.dunning.sweep_dunning_rules")
def sweep_dunning_rules() -> int:
    """Regra 10: job diário — varre todos os tenants ativos."""
    return asyncio.run(_sweep_all_tenants(date.today()))
