"""Limpeza da auditoria de chamadas externas (spec 041, §4 — retenção de 30 dias).

Roda como superusuário (MIGRATIONS_DATABASE_URL) porque a tabela tem FORCE RLS e
a purga é cross-tenant — mesmo padrão do refresh da matview em workers/scores.py.
Nenhum teste importa este módulo (workers ficam fora do caminho testado — ver
workers/celery_app.py); a regra testada é a gravação, que mora no DbAuditSink.
"""

import asyncio

from sqlalchemy import delete, func, text

from app.core.bootstrap import migrations_url
from app.core.db import create_engine_from_url
from app.domain.external_requests.models import ExternalRequest
from app.workers.celery_app import celery_app

RETENTION_DAYS = 30


@celery_app.task(name="app.workers.external_requests.purge_external_requests")
def purge_external_requests() -> int:
    """Apaga registros com mais de 30 dias. Devolve quantas linhas saíram."""
    return asyncio.run(_purge())


async def _purge() -> int:
    url = migrations_url("a purga cross-tenant de requisições externas")
    engine = create_engine_from_url(url)
    try:
        async with engine.begin() as conn:
            result = await conn.execute(
                delete(ExternalRequest).where(
                    ExternalRequest.created_at
                    < func.now() - text(f"interval '{RETENTION_DAYS} days'")
                )
            )
            return result.rowcount
    finally:
        await engine.dispose()
