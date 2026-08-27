"""App Celery do Rito — broker e backend no Redis; agendamentos no beat.

O worker e o beat sobem separados do uvicorn (`celery -A app.workers.celery_app worker
--beat`). Nenhum teste importa este módulo: as regras de negócio ficam nos services e
são exercitadas direto, sem fila (CLAUDE.md §3 — teste não toca rede nem broker).
"""

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

# Import por efeito colateral: registra os sinais que propagam request_id e traceparent
# da requisição para a task (spec 097, regras 2 e 5). Precisa acontecer no processo que
# enfileira E no que executa — ambos importam este módulo para achar o `celery_app`.
from app.workers import observability  # noqa: F401

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
    # Spec 078: um único tick por minuto refresca SEQUENCIALMENTE as views vencidas
    # conforme o intervalo do aggregate_registry (BI 8 h, produtividade/agilidade
    # 15 min, saldo diário 10 min), com log e alerta de refresh lento. Substitui os
    # beats individuais das specs 039/059/071/073/074/075/076/077 — os workers de
    # domínio continuam existindo porque os testes chamam os wrappers async direto.
    "aggregates-refresh-due": {
        "task": "app.workers.aggregates.refresh_due_aggregates",
        "schedule": crontab(),
    },
    # Spec 092: acorda execução cujo atraso venceu e publica os lançamentos que
    # vencem hoje. De 15 em 15 minutos — uma automação com atraso em DIAS não precisa
    # de precisão de minuto, e a varredura é uma consulta por índice parcial.
    "automations-sweep": {
        "task": "app.workers.automations.sweep_automations",
        "schedule": crontab(minute="*/15"),
    },
    # Spec 093: o backoff de 1/5/15 minutos precisa de um tick de minuto para caber.
    "webhooks-retry-due": {
        "task": "app.workers.webhooks.sweep_webhook_deliveries",
        "schedule": crontab(),
    },
    # Spec 034, regra 2: varredura diária das séries de recorrência atrasadas.
    "post-recurrence-sweep": {
        "task": "app.workers.recurrences.sweep_recurrences",
        "schedule": crontab(hour=3, minute=12),
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
    # Spec 061, regra 10: régua de cobrança diária (DUNNING_SYNC_CRON).
    "dunning-sweep": {
        "task": "app.workers.dunning.sweep_dunning_rules",
        "schedule": _daily_crontab(_settings.dunning_sync_cron),
    },
    # Spec 073, regra 9: expurgo mensal de access_logs além da retenção de 12 meses.
    # Refatoração 080: o log de refresh crescia sem teto (uma linha por view por
    # minuto) — expurgo diário com retenção de 90 dias.
    "aggregate-refresh-log-purge": {
        "task": "app.workers.aggregates.purge_refresh_log",
        "schedule": crontab(hour=4, minute=20),
    },
    # Spec 082, regras 4 e 12: espera humana morre em 24 h, thread concluído em 90 dias.
    "ai-threads-expire": {
        "task": "app.workers.ai_threads.expire_waiting",
        "schedule": crontab(minute=25),
    },
    # Spec 084, regra 4: a proposta de escrita expira em 1 h — a varredura é de 10 em
    # 10 min porque a janela é curta.
    # Spec 086, regra 10: leitura automática das intimações novas, de hora em hora, só
    # para quem ligou a opção.
    "publication-analysis": {
        "task": "app.workers.publication_analysis.analyze_pending",
        "schedule": crontab(minute=40),
    },
    "ai-actions-expire": {
        "task": "app.workers.ai_threads.expire_actions",
        "schedule": crontab(minute="*/10"),
    },
    "ai-threads-purge": {
        "task": "app.workers.ai_threads.purge_old",
        "schedule": crontab(hour=4, minute=35),
    },
    "access-logs-purge": {
        "task": "app.workers.timesheet.purge_access_logs",
        "schedule": crontab(day_of_month=1, hour=4, minute=0),
    },
}

# Garante que o worker registra as tasks declaradas fora deste módulo.
celery_app.conf.imports = (
    "app.workers.aggregates",
    "app.workers.recurrences",
    "app.workers.scores",
    "app.workers.external_requests",
    "app.workers.djen_sync",
    "app.workers.datajud_sync",
    "app.workers.integration_health",
    "app.workers.stagnation",
    "app.workers.financial_recurrence",
    "app.workers.financial_dashboard",
    "app.workers.dunning",
    "app.workers.agility",
    "app.workers.timesheet",
    "app.workers.bi_pipeline",
    "app.workers.bi_vintage",
    "app.workers.bi_cycles",
    "app.workers.bi_costs",
)
