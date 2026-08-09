"""Refresh da view materializada user_monthly_scores (spec 039, regra 9).

Duas particularidades da materialized view num setup com RLS:

- REFRESH exige ser dono da view E enxergar todas as linhas; a role de aplicação
  (rito_app) está sob FORCE RLS e sem `app.tenant_id` veria zero linhas — o refresh
  esvaziaria a view. Por isso o worker conecta com a MIGRATIONS_DATABASE_URL
  (superusuário), como faz a fixture admin_engine dos testes.
- REFRESH ... CONCURRENTLY não roda dentro de transação, então a conexão vai em
  AUTOCOMMIT.

O agendamento imediato (concluir/reabrir tarefa) é feito pelo posts router via
`schedule_scores_refresh` — com countdown curto para o commit da request acontecer
antes do refresh; se o broker estiver fora, a conclusão NUNCA falha por causa disso
(o beat de 15 min cobre). Como toda a camada de fila, não é exercitada em teste
(CLAUDE.md §3) — a regra testada é o próprio REFRESH, chamado direto nos testes.
"""

import asyncio
import logging

from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import create_engine_from_url
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


async def refresh_user_monthly_scores(url: str | None = None) -> None:
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
            await conn.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY user_monthly_scores"))
        finally:
            await conn.close()
    finally:
        await engine.dispose()


@celery_app.task(name="app.workers.scores.refresh_scores")  # type: ignore[untyped-decorator]
def refresh_scores() -> None:
    asyncio.run(refresh_user_monthly_scores())


def schedule_scores_refresh(countdown: float = 5.0) -> None:
    """Agenda um refresh quase imediato após concluir/reabrir tarefa (regra 9).

    No ambiente de teste é no-op proposital: teste não toca o broker (CLAUDE.md §3) —
    os testes chamam `refresh_user_monthly_scores` direto, sem fila."""
    if get_settings().app_env == "test":
        return
    try:
        celery_app.send_task("app.workers.scores.refresh_scores", countdown=countdown)
    except Exception:  # broker fora do ar não pode derrubar a conclusão da tarefa
        logger.warning("Falha ao agendar refresh do taskscore — o beat de 15 min cobre.")
