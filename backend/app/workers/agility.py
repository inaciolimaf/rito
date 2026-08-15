"""Refresh da view materializada agility_daily (spec 071, regra 10).

Mesmo molde de app/workers/scores.py — a mecânica de REFRESH (AUTOCOMMIT,
superusuário) é compartilhada em app/core/materialized_view.py. Não exercitado em
teste (CLAUDE.md §3): os testes chamam `refresh_agility_daily` direto.
"""

import asyncio

from app.core.materialized_view import refresh_materialized_view_concurrently
from app.workers.celery_app import celery_app


async def refresh_agility_daily(url: str | None = None) -> None:
    """Wrapper fino — nome/assinatura preservados porque os testes chamam esta
    função direto, sem passar pela fila."""
    await refresh_materialized_view_concurrently("agility_daily", url)


@celery_app.task(name="app.workers.agility.refresh_agility")  # type: ignore[untyped-decorator]
def refresh_agility() -> None:
    asyncio.run(refresh_agility_daily())
