"""Livro de ponto (spec 073): refresh de timesheet_daily (mesmo molde de
app/workers/scores.py) e expurgo mensal de access_logs além da retenção de 12 meses
(regra 9, mesmo padrão de varredura por tenant de app/workers/stagnation.py).
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.core.db import create_engine, create_session_factory
from app.core.materialized_view import refresh_materialized_view_concurrently
from app.core.models import Tenant
from app.core.rls import set_tenant_context
from app.domain.reports.models import AccessLog
from app.workers.celery_app import celery_app

_RETENTION_DAYS = 365


async def refresh_timesheet_daily(url: str | None = None) -> None:
    """Wrapper fino — nome/assinatura preservados porque os testes chamam esta
    função direto, sem passar pela fila (CLAUDE.md §3)."""
    await refresh_materialized_view_concurrently("timesheet_daily", url)


@celery_app.task(name="app.workers.timesheet.refresh_timesheet")  # type: ignore[untyped-decorator]
def refresh_timesheet() -> None:
    asyncio.run(refresh_timesheet_daily())


async def _purge_tenant(tenant_id: uuid.UUID, cutoff: datetime) -> int:
    engine = create_engine()
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session, session.begin():
            await set_tenant_context(session, tenant_id)
            result = await session.execute(delete(AccessLog).where(AccessLog.occurred_at < cutoff))
            # DELETE via ORM session sempre devolve CursorResult em runtime; a
            # assinatura de session.execute() só declara o Result[Any] genérico.
            return int(result.rowcount)  # type: ignore[attr-defined]
    finally:
        await engine.dispose()


async def purge_access_logs() -> int:
    cutoff = datetime.now(UTC) - timedelta(days=_RETENTION_DAYS)
    engine = create_engine()
    session_factory = create_session_factory(engine)
    total = 0
    try:
        async with session_factory() as session:
            tenant_ids = (
                await session.scalars(select(Tenant.id).where(Tenant.is_active.is_(True)))
            ).all()
        for tenant_id in tenant_ids:
            total += await _purge_tenant(tenant_id, cutoff)
    finally:
        await engine.dispose()
    return total


@celery_app.task(name="app.workers.timesheet.purge_access_logs")  # type: ignore[untyped-decorator]
def purge_access_logs_task() -> int:
    """Regra 9: job mensal — retenção de 12 meses."""
    return asyncio.run(purge_access_logs())
