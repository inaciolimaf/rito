"""App Celery do Rito — broker e backend no Redis; agendamentos no beat.

O worker e o beat sobem separados do uvicorn (`celery -A app.workers.celery_app worker
--beat`). Nenhum teste importa este módulo: as regras de negócio ficam nos services e
são exercitadas direto, sem fila (CLAUDE.md §3 — teste não toca rede nem broker).
"""

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

_settings = get_settings()

celery_app = Celery("rito", broker=_settings.redis_url, backend=_settings.redis_url)


def _daily_crontab(expression: str) -> crontab:
    """Crontab a partir de um *_SYNC_CRON ("m h * * *" — 5 campos, diário).

    A forma diária é exigida porque o cálculo de `next_sync_at`
    (domain/monitored_terms/sync.next_daily_run) só sabe avançar um dia; um
    cron semanal agendaria o beat certo mas marcaria o próximo run errado.
    Falhar no boot é melhor que agendar errado em silêncio.
    """
    parts = expression.split()
    if len(parts) != 5 or parts[2] != "*" or parts[3] != "*" or parts[4] != "*":
        raise ValueError(f"*_SYNC_CRON precisa ser diário ('m h * * *'), recebido: {expression!r}")
    return crontab(minute=parts[0], hour=parts[1])


celery_app.conf.beat_schedule = {
    # Spec 034, regra 2: varredura diária das séries de recorrência atrasadas.
    "post-recurrence-sweep": {
        "task": "app.workers.recurrences.sweep_recurrences",
        "schedule": crontab(hour=3, minute=12),
    },
    # Spec 039, regra 9: refresh da view materializada de pontuação a cada 15 min
    # (concluir tarefa também agenda um refresh imediato — ver workers/scores.py).
    "taskscore-refresh": {
        "task": "app.workers.scores.refresh_scores",
        "schedule": crontab(minute="*/15"),
    },
    # Spec 041, §4: retenção de 30 dias da auditoria de chamadas externas.
    "external-requests-purge": {
        "task": "app.workers.external_requests.purge_external_requests",
        "schedule": crontab(hour=4, minute=7),
    },
    # Spec 044: varredura diária dos termos monitorados (DJEN_SYNC_CRON).
    "djen-sync": {
        "task": "app.workers.djen_sync.sync_due_terms",
        "schedule": _daily_crontab(_settings.djen_sync_cron),
    },
    # Spec 047: varredura diária de andamentos via DataJud (DATAJUD_SYNC_CRON).
    "datajud-sync": {
        "task": "app.workers.datajud_sync.sync_due_movements",
        "schedule": _daily_crontab(_settings.datajud_sync_cron),
    },
    # Spec 049: saúde das integrações + taxa de vínculo automático por tenant
    # (INTEGRATION_HEALTH_CRON).
    "integration-health": {
        "task": "app.workers.integration_health.run_daily_health_check",
        "schedule": _daily_crontab(_settings.integration_health_cron),
    },
    # Spec 052, regra 4: recálculo diário de estagnação do CRM, às 3h.
    "stagnation-sweep": {
        "task": "app.workers.stagnation.sweep_all_tenants",
        "schedule": crontab(hour=3, minute=0),
    },
    # Spec 057, regra 4: recorrência financeira nunca gera tudo de uma vez — varredura
    # mensal (dia 1, 3h30) mantém `generated_until` sempre 3 meses à frente.
    "financial-recurrence-sweep": {
        "task": "app.workers.financial_recurrence.sweep_financial_recurrences",
        "schedule": crontab(day_of_month=1, hour=3, minute=30),
    },
}

# Garante que o worker registra as tasks declaradas fora deste módulo.
celery_app.conf.imports = (
    "app.workers.recurrences",
    "app.workers.scores",
    "app.workers.external_requests",
    "app.workers.djen_sync",
    "app.workers.datajud_sync",
    "app.workers.integration_health",
    "app.workers.stagnation",
    "app.workers.financial_recurrence",
)
