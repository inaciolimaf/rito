"""Refresh da view materializada bi_vintage (spec 075, §4 — a cada 8 h, como a 074).

Mesmo molde de app/workers/bi_pipeline.py — a mecânica de REFRESH (AUTOCOMMIT,
superusuário) é compartilhada em app/core/materialized_view.py. Não exercitado via
fila em teste (CLAUDE.md §3): os testes chamam `refresh_bi_vintage` direto.
"""

import asyncio

from app.core.materialized_view import refresh_materialized_view_concurrently
from app.workers.celery_app import celery_app


async def refresh_bi_vintage(url: str | None = None) -> None:
    """Wrapper fino — os testes chamam esta função direto com a
    MIGRATIONS_DATABASE_URL de teste, sem passar pela fila."""
    await refresh_materialized_view_concurrently("bi_vintage", url)


@celery_app.task(name="app.workers.bi_vintage.refresh_bi_vintage_view")  # type: ignore[untyped-decorator]
def refresh_bi_vintage_view() -> None:
    asyncio.run(refresh_bi_vintage())
