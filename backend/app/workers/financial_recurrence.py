"""Varredura mensal das séries de recorrência financeira (spec 057, regra 4).

Mesmo padrão de `app/workers/recurrences.py` (spec 034): RLS filtra por
`app.tenant_id`, então a varredura roda tenant a tenant; a regra em si mora em
`TransactionSeriesService.sweep_recurring`, testada sem fila.
"""

import asyncio
from datetime import date

from sqlalchemy import select

from app.core.db import create_engine, create_session_factory
from app.core.models import Tenant
from app.core.rls import set_tenant_context
from app.domain.financial.service import TransactionSeriesService
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.financial_recurrence.sweep_financial_recurrences")  # type: ignore[untyped-decorator]
def sweep_financial_recurrences() -> int:
    """Gera as próximas ocorrências (até 3 meses à frente) de todas as séries de
    recorrência ativas, em todos os tenants. Devolve o total gerado."""
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
                service = TransactionSeriesService(session=session, tenant_id=tenant_id)
                generated += await service.sweep_recurring(date.today())
    finally:
        await engine.dispose()
    return generated
