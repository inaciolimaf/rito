"""Orquestrador de refresh das views materializadas (spec 078).

Três responsabilidades:

1. `refresh_aggregate` — REFRESH MATERIALIZED VIEW CONCURRENTLY (regra 3) com log em
   `aggregate_refresh_log` e atualização do `aggregate_registry`; refresh acima de
   60 s gera alerta em `integration_alerts` (regra 9). Como todo refresh de matview
   neste setup, roda como superusuário em AUTOCOMMIT (ver app/core/materialized_view.py).
2. `refresh_due_aggregates` — o beat (a cada minuto) chama esta função, que refresca
   SEQUENCIALMENTE (regra 10) só as views vencidas conforme o intervalo do registry
   (regra 2); falha em uma não impede as outras (regra 11). Substitui os oito beats
   individuais das specs 039–077.
3. `schedule_aggregate_refresh` — invalidação por evento (regras 4 e 5): agenda o
   refresh com countdown curto (≤ 1 min, tempo do commit da request acontecer) sem
   bloquear a operação que disparou; broker fora nunca derruba a operação. No
   ambiente de teste é no-op proposital (CLAUDE.md §3) — os testes chamam
   `refresh_aggregate`/`refresh_due_aggregates` direto com a
   MIGRATIONS_DATABASE_URL de teste.

`EVENT_TO_VIEWS` espelha a coluna `invalidate_on` semeada na migration 078 — mudou
um, muda o outro.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import get_settings
from app.core.db import create_engine_from_url
from app.core.materialized_view import MATERIALIZED_VIEWS
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Regra 9: refresh que passa de 60 s gera alerta — a view precisa de otimização.
SLOW_REFRESH_ALERT_SECONDS = 60
# Retenção do log de refresh (refatoração 080) — mesmo horizonte de `sync_runs`.
REFRESH_LOG_RETENTION_DAYS = 90
_SLOW_ALERT_INTEGRATION = "aggregates"
_SLOW_ALERT_CODE = "slow_refresh"

# Regras 4 e 5: evento de domínio → views que ele invalida. Espelha `invalidate_on`
# do seed da migration 078. Views já cobertas por agendamento próprio em specs
# anteriores (user_monthly_scores na 039, account_daily_balances na 059) entram aqui
# e os hooks antigos foram substituídos por este — um único caminho de invalidação,
# sempre com log no registry.
EVENT_TO_VIEWS: dict[str, tuple[str, ...]] = {
    "task.completed": ("user_monthly_scores", "agility_daily", "bi_cost_allocation"),
    "transaction.paid": ("account_daily_balances", "bi_lawsuit_cycles", "bi_cost_allocation"),
    "lawsuit.closed": ("bi_pipeline_monthly", "bi_vintage", "bi_lawsuit_cycles"),
    "lawsuit.archived": ("bi_pipeline_monthly", "bi_vintage", "bi_lawsuit_cycles"),
}

_KNOWN_VIEWS = {spec.view_name for spec in MATERIALIZED_VIEWS}


@dataclass(frozen=True)
class RefreshOutcome:
    name: str
    duration_ms: int
    rows_affected: int


async def _refresh_view(conn: AsyncConnection, name: str) -> None:
    """Isolada para os testes simularem falha/lentidão sem tocar o banco."""
    # Identificador de view não vai como bind param — o nome só vem do registry/
    # MATERIALIZED_VIEWS, nunca de entrada externa (mesmo padrão do helper da 060).
    await conn.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {name}"))


async def _maybe_alert_slow_refresh(conn: AsyncConnection, name: str, duration_ms: int) -> None:
    """Regra 9: refresh > 60 s vira alerta de sistema (tenant_id NULL, como os
    alertas de config global da 046/049), deduplicado por view enquanto aberto."""
    existing = await conn.execute(
        text(
            "SELECT 1 FROM integration_alerts "
            "WHERE integration = :integration AND code = :code AND resolved_at IS NULL "
            "AND message LIKE :pattern LIMIT 1"
        ),
        {
            "integration": _SLOW_ALERT_INTEGRATION,
            "code": _SLOW_ALERT_CODE,
            "pattern": f"{name}:%",
        },
    )
    if existing.first() is not None:
        return
    await conn.execute(
        text(
            "INSERT INTO integration_alerts (tenant_id, integration, severity, code, message) "
            "VALUES (NULL, :integration, 'warning', :code, :message)"
        ),
        {
            "integration": _SLOW_ALERT_INTEGRATION,
            "code": _SLOW_ALERT_CODE,
            "message": (
                f"{name}: refresh levou {duration_ms // 1000} s "
                f"(limite {SLOW_REFRESH_ALERT_SECONDS} s) — a view precisa de otimização."
            ),
        },
    )


def _refresh_url(name: str, url: str | None) -> str:
    """A URL do refresh, com o nome da view já validado contra a allowlist.

    As duas recusas ficam juntas porque as duas são «não dá para nem começar»: view fora do
    `MATERIALIZED_VIEWS` seria identificador vindo de lugar nenhum, e sem
    `MIGRATIONS_DATABASE_URL` não há conexão de superusuário para dar `REFRESH`.
    """
    if name not in _KNOWN_VIEWS:
        raise ValueError(f"View não registrada em MATERIALIZED_VIEWS: {name!r}")
    resolved = url or get_settings().migrations_database_url
    if resolved is None:
        raise RuntimeError("MIGRATIONS_DATABASE_URL não configurada para o refresh.")
    return resolved


async def _record_failure(conn: AsyncConnection, name: str, log_id: int, exc: Exception) -> None:
    """Regra 7: a falha é registrada nos DOIS lugares e o dado velho continua servindo.

    `last_refresh_at` não é tocado de propósito — a view ainda tem o conteúdo da última
    execução boa, e quem lê o painel precisa saber que ele está velho, não que sumiu.
    """
    await conn.execute(
        text(
            "UPDATE aggregate_refresh_log SET finished_at = now(), error = :error "
            "WHERE id = :log_id"
        ),
        {"error": str(exc)[:500], "log_id": log_id},
    )
    await conn.execute(
        text("UPDATE aggregate_registry SET last_error = :error WHERE name = :name"),
        {"error": str(exc)[:500], "name": name},
    )


async def _record_success(
    conn: AsyncConnection, name: str, log_id: int, rows_affected: int, duration_ms: int
) -> None:
    """Fecha o log e atualiza o registry — inclusive limpando o `last_error` anterior.

    Limpar é o par de `_record_failure`: sem isso, uma view que falhou uma vez carregaria
    o erro para sempre no painel, mesmo depois de voltar a atualizar.
    """
    await conn.execute(
        text(
            "UPDATE aggregate_refresh_log "
            "SET finished_at = now(), rows_affected = :rows WHERE id = :log_id"
        ),
        {"rows": rows_affected, "log_id": log_id},
    )
    await conn.execute(
        text(
            "UPDATE aggregate_registry SET last_refresh_at = now(), "
            "last_refresh_duration_ms = :duration, last_error = NULL WHERE name = :name"
        ),
        {"duration": duration_ms, "name": name},
    )


async def _refresh_and_log(conn: AsyncConnection, name: str, log_id: int) -> RefreshOutcome:
    """Recarrega a view, mede quanto levou e registra o desfecho.

    A falha é gravada ANTES de subir (regra 7): `last_refresh_at` fica como estava e o dado
    velho continua servindo — um painel com número de ontem é melhor que um painel vazio —,
    mas `last_error` passa a dizer que a última tentativa falhou.
    """
    started = monotonic()
    try:
        await _refresh_view(conn, name)
    except Exception as exc:
        await _record_failure(conn, name, log_id, exc)
        raise
    duration_ms = int((monotonic() - started) * 1000)
    # `# noqa: S608`: `name` é validado contra `_KNOWN_VIEWS` na entrada de
    # `refresh_aggregate` — só passa nome que está em `MATERIALIZED_VIEWS`. Identificador
    # não vai como bind param; a allowlist é a defesa real.
    rows_affected = (
        await conn.execute(text(f"SELECT count(*) FROM {name}"))  # noqa: S608
    ).scalar_one()
    await _record_success(conn, name, log_id, rows_affected, duration_ms)
    if duration_ms > SLOW_REFRESH_ALERT_SECONDS * 1000:
        await _maybe_alert_slow_refresh(conn, name, duration_ms)
    return RefreshOutcome(name=name, duration_ms=duration_ms, rows_affected=rows_affected)


async def refresh_aggregate(name: str, url: str | None = None) -> RefreshOutcome:
    """Refresh logado de UMA view. Em falha, registra o erro no log e em
    `last_error` (mantendo `last_refresh_at` anterior — o dado velho continua
    servindo, regra 7) e PROPAGA a exceção; quem decide seguir em frente é o
    orquestrador (`refresh_due_aggregates`) ou o endpoint de refresh manual."""
    engine = create_engine_from_url(_refresh_url(name, url))
    try:
        conn = await engine.connect()
        try:
            await conn.execution_options(isolation_level="AUTOCOMMIT")
            log_id = (
                await conn.execute(
                    text("INSERT INTO aggregate_refresh_log (name) VALUES (:name) RETURNING id"),
                    {"name": name},
                )
            ).scalar_one()
            return await _refresh_and_log(conn, name, log_id)
        finally:
            await conn.close()
    finally:
        await engine.dispose()


async def refresh_due_aggregates(url: str | None = None) -> list[str]:
    """Refresh sequencial (regra 10) das views vencidas ou nunca refrescadas.
    Falha em uma não impede as outras (regra 11) — o erro fica no registry/log.
    Devolve os nomes das views efetivamente refrescadas (para os testes)."""
    resolved = url or get_settings().migrations_database_url
    if resolved is None:
        raise RuntimeError("MIGRATIONS_DATABASE_URL não configurada para o refresh.")
    engine = create_engine_from_url(resolved)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT name, refresh_interval_seconds, last_refresh_at "
                        "FROM aggregate_registry WHERE is_enabled ORDER BY name"
                    )
                )
            ).all()
    finally:
        await engine.dispose()
    now = datetime.now(UTC)
    refreshed: list[str] = []
    for name, interval_seconds, last_refresh_at in rows:
        due = last_refresh_at is None or (now - last_refresh_at).total_seconds() >= interval_seconds
        if not due:
            continue
        try:
            await refresh_aggregate(name, resolved)
            refreshed.append(name)
        except Exception:
            logger.warning("Refresh do agregado %s falhou — as demais views seguem.", name)
    return refreshed


def schedule_aggregate_refresh(event: str, countdown: float = 5.0) -> None:
    """Agenda o refresh das views invalidadas por `event` (regra 4: em até 1 min,
    sem bloquear a operação que disparou — o countdown cobre o commit da request).

    No ambiente de teste é no-op proposital: teste não toca o broker (CLAUDE.md §3)."""
    if get_settings().app_env == "test":
        return
    for view_name in EVENT_TO_VIEWS.get(event, ()):
        try:
            celery_app.send_task(
                "app.workers.aggregates.refresh_aggregate_by_name",
                args=[view_name],
                countdown=countdown,
            )
        except Exception:  # broker fora do ar não pode derrubar a operação de domínio
            logger.warning(
                "Falha ao agendar refresh de %s (%s) — o beat de 1 min cobre.",
                view_name,
                event,
            )


@celery_app.task(name="app.workers.aggregates.refresh_aggregate_by_name")
def refresh_aggregate_by_name(name: str) -> None:
    asyncio.run(refresh_aggregate(name))


@celery_app.task(name="app.workers.aggregates.refresh_due_aggregates")
def refresh_due_aggregates_task() -> None:
    asyncio.run(refresh_due_aggregates())


async def purge_refresh_log(url: str | None = None) -> int:
    """Retenção de `aggregate_refresh_log` (refatoração 080).

    O beat de 1 min escreve uma linha por view refrescada: em regime, algo entre 10 e
    12 mil linhas por dia. A spec 078 criou a tabela sem expurgo — a auditoria da 080
    encontrou a única tabela de crescimento ilimitado do banco. 90 dias é o suficiente
    para investigar uma degradação de refresh (é o mesmo horizonte de `sync_runs`).
    """
    resolved = url or get_settings().migrations_database_url
    if resolved is None:
        raise RuntimeError("MIGRATIONS_DATABASE_URL não configurada para o expurgo.")
    engine = create_engine_from_url(resolved)
    try:
        async with engine.begin() as conn:
            # Spec 115: a retenção ia interpolada no SQL. `make_interval` aceita o número
            # como parâmetro ligado, então nada mais é montado por string aqui.
            result = await conn.execute(
                text(
                    "DELETE FROM aggregate_refresh_log "
                    "WHERE started_at < now() - make_interval(days => :dias)"
                ),
                {"dias": REFRESH_LOG_RETENTION_DAYS},
            )
            return int(result.rowcount)
    finally:
        await engine.dispose()


@celery_app.task(name="app.workers.aggregates.purge_refresh_log")
def purge_refresh_log_task() -> int:
    return asyncio.run(purge_refresh_log())
