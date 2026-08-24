"""Refresh da view materializada bi_pipeline_monthly (spec 074, regra 8).

Mesmo molde de app/workers/agility.py — a mecânica de REFRESH (AUTOCOMMIT,
superusuário) é compartilhada em app/core/materialized_view.py. Não exercitado via
fila em teste (CLAUDE.md §3): os testes chamam `refresh_bi_pipeline_monthly` direto.
"""

import asyncio

from app.core.materialized_view import refresh_materialized_view_concurrently
from app.workers.celery_app import celery_app


async def refresh_bi_pipeline_monthly(url: str | None = None) -> None:
    """Wrapper fino — os testes chamam esta função direto com a
    MIGRATIONS_DATABASE_URL de teste, sem passar pela fila."""
    await refresh_materialized_view_concurrently("bi_pipeline_monthly", url)


@celery_app.task(name="app.workers.bi_pipeline.refresh_bi_pipeline")  # type: ignore[untyped-decorator]
def refresh_bi_pipeline() -> None:
    asyncio.run(refresh_bi_pipeline_monthly())
