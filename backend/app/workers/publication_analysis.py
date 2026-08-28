"""Leitura automática de intimações (spec 086, regra 10).

Roda só para o escritório que ligou a opção — análise custa token, e o padrão é
desligado. Varre o que chegou e ainda não foi lido, em lotes pequenos: intimação
acumulada por um dia é aborrecimento; conta de IA inesperada é problema.
"""

import asyncio
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import create_engine, create_session_factory
from app.core.models import Tenant
from app.core.rls import set_tenant_context
from app.domain.ai.service import AiRunner
from app.domain.publications.analysis import PublicationAnalysisService
from app.integrations.openrouter.factory import create_llm_provider
from app.integrations.openrouter.types import LLMProvider
from app.workers.celery_app import celery_app

logger = logging.getLogger("rito.ai.publications")

# Teto por execução e por escritório — o beat roda de novo daqui a pouco.
BATCH_SIZE = 20


async def analyze_pending_publications(*, batch_size: int = BATCH_SIZE) -> dict[str, int]:
    engine = create_engine()
    session_factory = create_session_factory(engine)
    provider = create_llm_provider()
    analisadas = escritorios = 0
    try:
        async with session_factory() as session:
            tenant_ids = (
                await session.scalars(select(Tenant.id).where(Tenant.is_active.is_(True)))
            ).all()
        for tenant_id in tenant_ids:
            analisadas += await _analyze_for_tenant(
                session_factory, tenant_id, provider, batch_size
            )
            escritorios += 1
    finally:
        await engine.dispose()
    return {"tenants": escritorios, "analyzed": analisadas}


async def _analyze_for_tenant(
    session_factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    provider: LLMProvider,
    batch_size: int,
) -> int:
    # Spec 100: os parâmetros eram `object` e o corpo silenciava dois erros. Tipá-los é
    # dizer a mesma coisa, uma vez, no lugar onde quem lê procura.
    async with session_factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        service = PublicationAnalysisService(
            session=session,
            tenant_id=tenant_id,
            runner=AiRunner(session, tenant_id, provider),
        )
        if not await service.auto_read_enabled():
            return 0
        pendentes = await service.analyses.publications_without_analysis(batch_size)
        total = 0
        for publication in pendentes:
            try:
                await service.analyze(publication)
                total += 1
            except Exception:
                # Uma intimação ilegível não pode parar a fila das outras (regra 10).
                logger.warning(
                    "Falha ao analisar a intimação %s — as demais seguem.", publication.id
                )
        return total


@celery_app.task(name="app.workers.publication_analysis.analyze_pending")
def analyze_pending_task() -> dict[str, int]:
    return asyncio.run(analyze_pending_publications())
