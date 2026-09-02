"""Varredura diária das séries de recorrência (spec 034, regra 2).

O RLS filtra por `app.tenant_id`, então a varredura roda tenant a tenant: lista os
tenants ativos (tabela sem RLS), abre uma transação por tenant com o contexto setado
e delega ao RecurrenceService — a regra em si mora lá e é testada sem fila.
"""

import asyncio

from sqlalchemy import select

from app.core.clock import Clock
from app.core.db import create_engine, create_session_factory
from app.core.models import Tenant
from app.core.rls import set_tenant_context
from app.domain.account.repository import AccountRepository
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
                # Spec 114, regra 3: o dia é o DO TENANT. A varredura roda para todos
                # os escritórios numa passada só, e usar um `date.today()` do processo
                # dava o mesmo dia para quem está em Lisboa e para quem está em Rio
                # Branco — seis fusos de diferença, e a régua disparando no dia errado
                # para quem não estivesse no fuso do servidor.
                hoje = Clock(await AccountRepository(session).timezone()).today()
                generated += await service.sweep_overdue(hoje)
    finally:
        await engine.dispose()
    return generated
