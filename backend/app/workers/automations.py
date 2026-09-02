"""Varredura das automações (spec 092).

Dois jobs diários/de minuto em minuto, ambos por tenant e ambos tolerantes a falha
individual — mesmo padrão da régua de cobrança (061) e da estagnação (052): um tenant com
problema não pode travar os outros.

Nenhum teste importa este módulo: a regra mora em `app/domain/automations/sweep.py` e é
exercitada direto, sem subir fila (CLAUDE.md §3).
"""

import asyncio
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import Clock
from app.core.db import create_engine, create_session_factory
from app.core.models import Tenant
from app.core.rls import set_tenant_context
from app.domain.account.repository import AccountRepository
from app.domain.automations.sweep import emit_overdue_transactions, resume_due_runs
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


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
                total += await _sweep_tenant(session_factory, tenant_id)
            except Exception:  # um tenant com problema não trava os demais
                logger.exception("automations: falha inesperada no tenant %s", tenant_id)
    finally:
        await engine.dispose()
    return total


async def _sweep_tenant(
    session_factory: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID
) -> int:
    async with session_factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        # Spec 114, regra 3: o dia é o DO TENANT. A varredura roda para todos
        # os escritórios numa passada só, e usar um `date.today()` do processo
        # dava o mesmo dia para quem está em Lisboa e para quem está em Rio
        # Branco — seis fusos de diferença, e a régua disparando no dia errado
        # para quem não estivesse no fuso do servidor.
        today = Clock(await AccountRepository(session).timezone()).today()
        vencidos = await emit_overdue_transactions(session, tenant_id, today=today)
        retomadas = await resume_due_runs(session, tenant_id)
        return vencidos + retomadas


@celery_app.task(name="app.workers.automations.sweep_automations")
def sweep_automations() -> int:
    return asyncio.run(_sweep())
