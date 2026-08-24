"""Refresh da view materializada bi_lawsuit_cycles (spec 076, §4 — a cada 8 h).

Mesmo molde de app/workers/bi_pipeline.py e bi_vintage.py — a mecânica de REFRESH
(AUTOCOMMIT, superusuário) é compartilhada em app/core/materialized_view.py. Não
exercitado via fila em teste (CLAUDE.md §3): os testes chamam `refresh_bi_cycles`
direto.
"""

import asyncio

from app.core.materialized_view import refresh_materialized_view_concurrently
from app.workers.celery_app import celery_app


async def refresh_bi_cycles(url: str | None = None) -> None:
    """Wrapper fino — os testes chamam esta função direto com a
    MIGRATIONS_DATABASE_URL de teste, sem passar pela fila."""
    await refresh_materialized_view_concurrently("bi_lawsuit_cycles", url)


@celery_app.task(name="app.workers.bi_cycles.refresh_bi_cycles_view")  # type: ignore[untyped-decorator]
def refresh_bi_cycles_view() -> None:
    asyncio.run(refresh_bi_cycles())
