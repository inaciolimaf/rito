"""Refresh da view materializada account_daily_balances (spec 059, regra 11).

Mesmo padrão de `app/workers/scores.py` (spec 039): REFRESH ... CONCURRENTLY não roda
dentro de transação (conexão em AUTOCOMMIT) e precisa do superusuário — a role de
aplicação está sob FORCE RLS e sem `app.tenant_id` setado veria zero linhas.

O agendamento imediato (baixa/estorno de lançamento) é feito por `TransactionService`
via `schedule_account_balances_refresh` — o beat de 10 min (regra 11) cobre o resto.
Como toda a camada de fila, não é exercitada em teste (CLAUDE.md §3); a regra testada
é o próprio REFRESH, chamado direto nos testes com a MIGRATIONS_DATABASE_URL.
"""

import asyncio
import logging

from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import create_engine_from_url
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


async def refresh_account_daily_balances(url: str | None = None) -> None:
    """REFRESH CONCURRENTLY como superusuário. Recebe a URL para os testes chamarem
    direto com a MIGRATIONS_DATABASE_URL de teste, sem passar pela fila."""
    resolved = url or get_settings().migrations_database_url
    if resolved is None:
        raise RuntimeError("MIGRATIONS_DATABASE_URL não configurada para o refresh.")
    engine = create_engine_from_url(resolved)
    try:
        conn = await engine.connect()
        try:
            # AUTOCOMMIT: REFRESH ... CONCURRENTLY não roda dentro de transação.
            await conn.execution_options(isolation_level="AUTOCOMMIT")
            await conn.execute(
                text("REFRESH MATERIALIZED VIEW CONCURRENTLY account_daily_balances")
            )
        finally:
            await conn.close()
    finally:
        await engine.dispose()


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
