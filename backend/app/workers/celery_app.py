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

celery_app.conf.beat_schedule = {
    # Spec 034, regra 2: varredura diária das séries de recorrência atrasadas.
    "post-recurrence-sweep": {
        "task": "app.workers.recurrences.sweep_recurrences",
        "schedule": crontab(hour=3, minute=12),
    },
}
