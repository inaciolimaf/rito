"""Refresh da view materializada account_daily_balances (spec 059, regra 11).

A mecânica de REFRESH (AUTOCOMMIT, superusuário) é compartilhada com todo worker de
matview — ver `app/core/materialized_view.py` (refatoração 060, Alvo 2).

O agendamento imediato (baixa/estorno de lançamento) é feito por `TransactionService`
via `schedule_account_balances_refresh` — o beat de 10 min (regra 11) cobre o resto.
Como toda a camada de fila, não é exercitada em teste (CLAUDE.md §3); a regra testada
é o próprio REFRESH, chamado direto nos testes com a MIGRATIONS_DATABASE_URL.
"""

import asyncio
import logging

from app.core.config import get_settings
from app.core.materialized_view import refresh_materialized_view_concurrently
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


async def refresh_account_daily_balances(url: str | None = None) -> None:
    """Wrapper fino — nome/assinatura preservados porque os testes de 059 chamam
    esta função direto, sem passar pela fila."""
    await refresh_materialized_view_concurrently("account_daily_balances", url)


@celery_app.task(name="app.workers.financial_dashboard.refresh_account_balances")  # type: ignore[untyped-decorator]
def refresh_account_balances() -> None:
    asyncio.run(refresh_account_daily_balances())


def schedule_account_balances_refresh(countdown: float = 5.0) -> None:
    """Agenda um refresh quase imediato após baixa/estorno (regra 11).

    No ambiente de teste é no-op proposital: teste não toca o broker (CLAUDE.md §3) —
    os testes chamam `refresh_account_daily_balances` direto, sem fila."""
    if get_settings().app_env == "test":
        return
    try:
        celery_app.send_task(
            "app.workers.financial_dashboard.refresh_account_balances", countdown=countdown
        )
    except Exception:  # broker fora do ar não pode derrubar a baixa/estorno
        logger.warning("Falha ao agendar refresh do saldo diário — o beat de 10 min cobre.")
