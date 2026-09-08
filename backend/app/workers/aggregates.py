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
import contextlib
import logging
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import Any

from sqlalchemy import Row, delete, func, insert, select, table, text, update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import get_settings
from app.core.db import create_engine_from_url
from app.core.materialized_view import MATERIALIZED_VIEWS
from app.core.sql import days_interval
from app.domain.aggregates.models import AggregateRefreshLog, AggregateRegistry
from app.domain.integration_alerts.models import IntegrationAlert
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Regra 9: refresh que passa de 60 s gera alerta — a view precisa de otimização.
SLOW_REFRESH_ALERT_SECONDS = 60
# Retenção do log de refresh (refatoração 080) — mesmo horizonte de `sync_runs`.
REFRESH_LOG_RETENTION_DAYS = 90
# Chave do advisory lock da varredura (spec 137). Diferente da 20260828 do
# `core/migrations.py` — advisory lock é um espaço de nomes só, e duas travas com o
# mesmo número seriam a mesma trava.
SWEEP_LOCK_KEY = 20260908
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
    """Isolada para os testes simularem falha/lentidão sem tocar o banco.

    `REFRESH MATERIALIZED VIEW` é DDL: o query builder não a monta, e é por isso que esta
    é uma das poucas linhas de SQL em string que a spec 127 deixou de pé (a lista inteira
    está em `tests/meta/test_sql_em_string.py`). Identificador de view não vai como bind
    param — o nome só vem do registry/MATERIALIZED_VIEWS, nunca de entrada externa (mesmo
    padrão do helper da 060).
    """
    await conn.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {name}"))


async def _maybe_alert_slow_refresh(conn: AsyncConnection, name: str, duration_ms: int) -> None:
    """Regra 9: refresh > 60 s vira alerta de sistema (tenant_id NULL, como os
    alertas de config global da 046/049), deduplicado por view enquanto aberto."""
    aberto = (
        select(IntegrationAlert.id)
        .where(
            IntegrationAlert.integration == _SLOW_ALERT_INTEGRATION,
            IntegrationAlert.code == _SLOW_ALERT_CODE,
            IntegrationAlert.resolved_at.is_(None),
            IntegrationAlert.message.like(f"{name}:%"),
        )
        .limit(1)
    )
    if (await conn.execute(aberto)).first() is not None:
        return
    await conn.execute(
        insert(IntegrationAlert).values(
            tenant_id=None,
            integration=_SLOW_ALERT_INTEGRATION,
            severity="warning",
            code=_SLOW_ALERT_CODE,
            message=(
                f"{name}: refresh levou {duration_ms // 1000} s "
                f"(limite {SLOW_REFRESH_ALERT_SECONDS} s) — a view precisa de otimização."
            ),
        )
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


async def _record_failure(
    conn: AsyncConnection, name: str, log_id: uuid.UUID, exc: Exception
) -> None:
    """Regra 7: a falha é registrada nos DOIS lugares e o dado velho continua servindo.

    `last_refresh_at` não é tocado de propósito — a view ainda tem o conteúdo da última
    execução boa, e quem lê o painel precisa saber que ele está velho, não que sumiu.
    """
    await conn.execute(
        update(AggregateRefreshLog)
        .where(AggregateRefreshLog.id == log_id)
        .values(finished_at=func.now(), error=str(exc)[:500])
    )
    await conn.execute(
        update(AggregateRegistry)
        .where(AggregateRegistry.name == name)
        .values(last_error=str(exc)[:500])
    )


async def _record_success(
    conn: AsyncConnection, name: str, log_id: uuid.UUID, rows_affected: int, duration_ms: int
) -> None:
    """Fecha o log e atualiza o registry — inclusive limpando o `last_error` anterior.

    Limpar é o par de `_record_failure`: sem isso, uma view que falhou uma vez carregaria
    o erro para sempre no painel, mesmo depois de voltar a atualizar.
    """
    await conn.execute(
        update(AggregateRefreshLog)
        .where(AggregateRefreshLog.id == log_id)
        .values(finished_at=func.now(), rows_affected=rows_affected)
    )
    await conn.execute(
        update(AggregateRegistry)
        .where(AggregateRegistry.name == name)
        .values(last_refresh_at=func.now(), last_refresh_duration_ms=duration_ms, last_error=None)
    )


async def _refresh_and_log(conn: AsyncConnection, name: str, log_id: uuid.UUID) -> RefreshOutcome:
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
    # `table(name)` em vez de f-string (spec 127): o nome da view é um IDENTIFICADOR, e o
    # builder o cita como tal em vez de concatená-lo num texto. A defesa real continua
    # sendo a allowlist — `name` é validado contra `_KNOWN_VIEWS` na entrada de
    # `refresh_aggregate` —, mas agora o `S608` do Bandit não tem o que apontar.
    rows_affected = (await conn.execute(select(func.count()).select_from(table(name)))).scalar_one()
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
                    insert(AggregateRefreshLog).values(name=name).returning(AggregateRefreshLog.id)
                )
            ).scalar_one()
            return await _refresh_and_log(conn, name, log_id)
        finally:
            await conn.close()
    finally:
        await engine.dispose()


async def _enabled_registry(url: str) -> Sequence[Row[Any]]:
    """As views ligadas no registry, com o intervalo e a hora do último refresh.

    Numa conexão à parte, fechada antes do primeiro refresh: `refresh_aggregate` abre a
    sua própria (precisa de AUTOCOMMIT), e segurar esta durante os N refreshes seria uma
    conexão de superusuário parada pelo tempo inteiro do beat.
    """
    engine = create_engine_from_url(url)
    try:
        async with engine.connect() as conn:
            return (
                await conn.execute(
                    select(
                        AggregateRegistry.name,
                        AggregateRegistry.refresh_interval_seconds,
                        AggregateRegistry.last_refresh_at,
                    )
                    .where(AggregateRegistry.is_enabled)
                    .order_by(AggregateRegistry.name)
                )
            ).all()
    finally:
        await engine.dispose()


@contextlib.asynccontextmanager
async def _sweep_lock(url: str) -> AsyncIterator[bool]:
    """Trava de sobreposição da varredura (spec 137), por advisory lock do Postgres.

    O beat roda de minuto em minuto e `last_refresh_at` só é escrito no FIM de cada
    refresh. Uma rodada que passe de um minuto — e existe alerta próprio para refresh
    acima de 60 s, então ela passa — deixa o tick seguinte considerar as MESMAS views
    vencidas e disparar `REFRESH MATERIALIZED VIEW CONCURRENTLY` duplicado: os dois
    serializam no lock da view, e o segundo é trabalho integralmente jogado fora, com
    uma conexão de superusuário parada esperando enquanto isso.

    `pg_try_advisory_lock` não espera: se a rodada anterior ainda está de pé, esta
    desiste e o próximo minuto tenta de novo. O lock é de SESSÃO e cai sozinho quando a
    conexão morre, então um worker que for morto no meio não deixa a varredura travada
    para sempre — que é a razão de ser advisory lock e não uma linha numa tabela.

    O custo é uma conexão parada durante a varredura. É o preço de não ter duas.
    """
    engine = create_engine_from_url(url)
    try:
        async with engine.connect() as conn:
            adquirido = bool(
                (await conn.execute(select(func.pg_try_advisory_lock(SWEEP_LOCK_KEY)))).scalar()
            )
            try:
                yield adquirido
            finally:
                if adquirido:
                    await conn.execute(select(func.pg_advisory_unlock(SWEEP_LOCK_KEY)))
    finally:
        await engine.dispose()


async def refresh_due_aggregates(url: str | None = None) -> list[str]:
    """Refresh sequencial (regra 10) das views vencidas ou nunca refrescadas.
    Falha em uma não impede as outras (regra 11) — o erro fica no registry/log.
    Devolve os nomes das views efetivamente refrescadas (para os testes).

    Spec 137: a varredura inteira roda sob advisory lock — ver `_sweep_lock`. Quando a
    trava está na mão de outra rodada, esta devolve lista vazia (nada foi refrescado
    por ela), que é exatamente o que o chamador precisa saber.
    """
    resolved = url or get_settings().migrations_database_url
    if resolved is None:
        raise RuntimeError("MIGRATIONS_DATABASE_URL não configurada para o refresh.")
    async with _sweep_lock(resolved) as adquirido:
        if not adquirido:
            logger.info("Varredura de agregados já em andamento — este tick não faz nada.")
            return []
        return await _refresh_due(resolved)


async def _refresh_due(url: str) -> list[str]:
    rows = await _enabled_registry(url)
    now = datetime.now(UTC)
    refreshed: list[str] = []
    for name, interval_seconds, last_refresh_at in rows:
        due = last_refresh_at is None or (now - last_refresh_at).total_seconds() >= interval_seconds
        if not due:
            continue
        try:
            await refresh_aggregate(name, url)
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
            # como parâmetro ligado, então nada mais é montado por string aqui — e desde a
            # 127 nem o comando é, `days_interval` é o mesmo `make_interval` pelo builder.
            result = await conn.execute(
                delete(AggregateRefreshLog).where(
                    AggregateRefreshLog.started_at
                    < func.now() - days_interval(REFRESH_LOG_RETENTION_DAYS)
                )
            )
            return int(result.rowcount)
    finally:
        await engine.dispose()


@celery_app.task(name="app.workers.aggregates.purge_refresh_log")
def purge_refresh_log_task() -> int:
    return asyncio.run(purge_refresh_log())
