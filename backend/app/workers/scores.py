"""Refresh da view materializada user_monthly_scores (spec 039, regra 9).

A mecânica de REFRESH (AUTOCOMMIT, superusuário) é compartilhada com todo worker de
matview — ver `app/core/materialized_view.py` (refatoração 060, Alvo 2).

O agendamento imediato (concluir/reabrir tarefa) é feito pelo posts router via
`schedule_scores_refresh` — com countdown curto para o commit da request acontecer
antes do refresh; se o broker estiver fora, a conclusão NUNCA falha por causa disso
(o beat de 15 min cobre). Como toda a camada de fila, não é exercitada em teste
(CLAUDE.md §3) — a regra testada é o próprio REFRESH, chamado direto nos testes.
"""

import asyncio
import logging

from app.core.config import get_settings
from app.core.materialized_view import refresh_materialized_view_concurrently
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


async def refresh_user_monthly_scores(url: str | None = None) -> None:
    """Wrapper fino — nome/assinatura preservados porque os testes de 039 chamam
    esta função direto, sem passar pela fila."""
    await refresh_materialized_view_concurrently("user_monthly_scores", url)


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
