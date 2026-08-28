"""Varredura diária das séries de recorrência (spec 034, regra 2).

O RLS filtra por `app.tenant_id`, então a varredura roda tenant a tenant: lista os
tenants ativos (tabela sem RLS), abre uma transação por tenant com o contexto setado
e delega ao RecurrenceService — a regra em si mora lá e é testada sem fila.
"""

import asyncio
from datetime import date

from sqlalchemy import select

from app.core.db import create_engine, create_session_factory
from app.core.models import Tenant
from app.core.rls import set_tenant_context
from app.domain.posts.recurrence_service import RecurrenceService
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.recurrences.sweep_recurrences")
def sweep_recurrences() -> int:
    """Gera as ocorrências atrasadas de todos os tenants. Devolve o total gerado."""
    return asyncio.run(_sweep_all_tenants())


async def _sweep_all_tenants() -> int:
    engine = create_engine()
    session_factory = create_session_factory(engine)
    generated = 0
    try:
        async with session_factory() as session:
            tenant_ids = (
                await session.scalars(select(Tenant.id).where(Tenant.is_active.is_(True)))
            ).all()
        for tenant_id in tenant_ids:
            async with session_factory() as session, session.begin():
                await set_tenant_context(session, tenant_id)
                service = RecurrenceService(session=session, tenant_id=tenant_id)
                generated += await service.sweep_overdue(date.today())
    finally:
        await engine.dispose()
    return generated
