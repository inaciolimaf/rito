"""Refresh da view materializada user_monthly_scores (spec 039, regra 9).

A mecânica de REFRESH (AUTOCOMMIT, superusuário) é compartilhada com todo worker de
matview — ver `app/core/materialized_view.py` (refatoração 060, Alvo 2).

Desde a spec 078 o agendamento (beat e invalidação por evento `task.completed`) é do
orquestrador `app/workers/aggregates.py`, com log no aggregate_registry. Este módulo
mantém só o wrapper async que os testes chamam direto, sem fila (CLAUDE.md §3).
"""

from app.core.materialized_view import refresh_materialized_view_concurrently


async def refresh_user_monthly_scores(url: str | None = None) -> None:
    """Wrapper fino — nome/assinatura preservados porque os testes de 039 chamam
    esta função direto, sem passar pela fila."""
    await refresh_materialized_view_concurrently("user_monthly_scores", url)
