"""Recálculo de estagnação do CRM (spec 052) — job diário (regra 4) e gatilho de
troca de `stagnant_days` (regra 10). Mover processo NÃO passa por aqui — é síncrono
dentro de `BoardService.change_stage`, sem fila (regra 4 "recalcula na hora").

Nenhum teste importa este módulo (mesmo padrão de `celery_app.py`/`recurrences.py`):
a regra em si mora em `StagnationService` e é exercitada direto, sem broker.
`schedule_stage_recalculation` segue o padrão de `workers/scores.py::
schedule_scores_refresh` — no-op em `app_env=test`, best-effort em produção.
"""

import asyncio
import logging
import uuid

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import create_engine, create_session_factory
from app.core.models import Tenant
from app.core.rls import set_tenant_context
from app.domain.lawsuits.stagnation_service import StagnationService
from app.domain.stages.repository import StageRepository
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _recalculate_tenant(tenant_id: uuid.UUID) -> int:
    engine = create_engine()
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session, session.begin():
            await set_tenant_context(session, tenant_id)
            service = StagnationService(session=session, tenant_id=tenant_id)
            return await service.recalculate_tenant()
    finally:
        await engine.dispose()


async def _recalculate_stage(stage_id: uuid.UUID, tenant_id: uuid.UUID) -> int:
    engine = create_engine()
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session, session.begin():
            await set_tenant_context(session, tenant_id)
            stage = await StageRepository(session).get_by_id(stage_id)
            if stage is None:
                return 0
            return await StagnationService(session=session, tenant_id=tenant_id).recalculate_stage(
                stage
            )
    finally:
        await engine.dispose()


async def _sweep_all_tenants() -> int:
    engine = create_engine()
    session_factory = create_session_factory(engine)
    total = 0
    try:
        async with session_factory() as session:
            tenant_ids = (
                await session.scalars(select(Tenant.id).where(Tenant.is_active.is_(True)))
            ).all()
        for tenant_id in tenant_ids:
            total += await _recalculate_tenant(tenant_id)
    finally:
        await engine.dispose()
    return total


@celery_app.task(name="app.workers.stagnation.sweep_all_tenants")  # type: ignore[untyped-decorator]
def sweep_all_tenants() -> int:
    """Regra 4: job diário às 3h — recalcula todos os tenants ativos."""
    return asyncio.run(_sweep_all_tenants())


@celery_app.task(name="app.workers.stagnation.recalculate_stage")  # type: ignore[untyped-decorator]
def recalculate_stage(stage_id: str, tenant_id: str) -> int:
    return asyncio.run(_recalculate_stage(uuid.UUID(stage_id), uuid.UUID(tenant_id)))


def schedule_stage_recalculation(stage_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    """Regra 10: mudar `stagnant_days`/`enable_stagnant_days` da etapa recalcula em
    background — no-op em teste, best-effort em produção (o job diário cobre)."""
    if get_settings().app_env == "test":
        return
    try:
        celery_app.send_task(
            "app.workers.stagnation.recalculate_stage",
            args=[str(stage_id), str(tenant_id)],
        )
    except Exception:  # broker fora do ar não pode derrubar a atualização da etapa
        logger.warning("Falha ao agendar recálculo de estagnação da etapa — o job diário cobre.")
