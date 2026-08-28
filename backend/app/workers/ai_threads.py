"""Manutenção das conversas de agente (spec 082, regras 4 e 12).

Duas varreduras diárias, no mesmo molde de `app/workers/timesheet.py`: expira quem
está esperando confirmação humana há mais de 24 h e apaga thread concluído com mais de
90 dias. Thread pendurado guarda estado com dado do escritório dentro — deixá-lo
esperando para sempre é um vazamento silencioso, não um detalhe de higiene.
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import create_engine, create_session_factory
from app.core.models import Tenant
from app.core.rls import set_tenant_context
from app.domain.ai.models import AiThread, ThreadStatus
from app.domain.ai.threads import THREAD_RETENTION_DAYS, AiThreadService
from app.workers.celery_app import celery_app

_FINISHED = (
    ThreadStatus.DONE.value,
    ThreadStatus.ERROR.value,
    ThreadStatus.CANCELLED.value,
)


# Spec 100: a assinatura era `func: object` e o corpo silenciava três erros com
# `type: ignore`. Um `Callable` tipado diz a mesma coisa que os três silenciamentos
# diziam juntos — e diz ANTES, para quem escrever a próxima varredura.
TenantTask = Callable[[AsyncSession, uuid.UUID], Awaitable[int]]


async def _for_each_tenant(func: TenantTask) -> int:
    engine = create_engine()
    session_factory = create_session_factory(engine)
    total = 0
    try:
        async with session_factory() as session:
            tenant_ids = (
                await session.scalars(select(Tenant.id).where(Tenant.is_active.is_(True)))
            ).all()
        for tenant_id in tenant_ids:
            async with session_factory() as session, session.begin():
                await set_tenant_context(session, tenant_id)
                total += await func(session, tenant_id)
    finally:
        await engine.dispose()
    return total


async def expire_waiting_threads() -> int:
    """Regra 4: 24 h sem confirmação → cancelado."""

    async def _expire(session: AsyncSession, tenant_id: uuid.UUID) -> int:
        service = AiThreadService(session=session, tenant_id=tenant_id)
        return await service.expire_waiting()

    return await _for_each_tenant(_expire)


async def purge_old_threads(*, now: datetime | None = None) -> int:
    """Regra 12: thread concluído com mais de 90 dias sai — os passos e checkpoints vão
    junto pela FK em cascata."""
    cutoff = (now or datetime.now(UTC)) - timedelta(days=THREAD_RETENTION_DAYS)

    async def _purge(session: AsyncSession, tenant_id: uuid.UUID) -> int:
        result = await session.execute(
            delete(AiThread).where(AiThread.status.in_(_FINISHED), AiThread.finished_at < cutoff)
        )
        # SQLAlchemy tipa `rowcount` só em `CursorResult`; um DELETE sempre devolve um.
        return int(result.rowcount)  # type: ignore[attr-defined]

    return await _for_each_tenant(_purge)


async def expire_pending_actions() -> int:
    """Spec 084, regra 4: proposta de escrita esquecida vira `expired` em 1 h.

    Fica no mesmo worker das threads porque é a mesma natureza: estado de IA parado
    esperando um humano que não voltou.
    """

    async def _expire(session: AsyncSession, tenant_id: uuid.UUID) -> int:
        from app.domain.ai.actions import AiActionService

        service = AiActionService(session=session, tenant_id=tenant_id)
        return await service.expire_pending()

    return await _for_each_tenant(_expire)


@celery_app.task(name="app.workers.ai_threads.expire_actions")
def expire_actions_task() -> int:
    return asyncio.run(expire_pending_actions())


@celery_app.task(name="app.workers.ai_threads.expire_waiting")
def expire_waiting_task() -> int:
    return asyncio.run(expire_waiting_threads())


@celery_app.task(name="app.workers.ai_threads.purge_old")
def purge_old_task() -> int:
    return asyncio.run(purge_old_threads())
