"""Varredura dos termos monitorados (spec 044).

Dois entry points Celery:
- `sync_due_terms` — beat diário (DJEN_SYNC_CRON): termos devidos + runs abertas
  (o sync manual da 043 abre a run e quem processa é esta varredura);
- `sync_term_by_id` — gatilho manual, agenda a execução do termo recém-aberto.

Cross-tenant: a listagem roda como superusuário (MIGRATIONS_DATABASE_URL) porque
monitored_terms tem FORCE RLS — mesmo padrão do refresh da matview em
workers/scores.py. Cada termo processa numa sessão por tenant; o TermSyncService
rearma `app.tenant_id` a cada commit (a persistência fica sob RLS de verdade).

Nenhum teste importa este módulo (ver workers/celery_app.py) — as regras moram
no TermSyncService e são exercitadas direto, sem fila nem broker.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.bootstrap import migrations_url
from app.core.config import Settings, get_settings
from app.core.db import create_engine_from_url, create_session_factory
from app.core.locks import RedisSyncLock
from app.core.redis import create_redis_client
from app.domain.monitored_terms.models import MonitoredTerm
from app.domain.monitored_terms.repository import MonitoredTermRepository
from app.domain.monitored_terms.sync import TermSyncService
from app.integrations.djen import DjenClient
from app.integrations.djen.source import DjenPublicationSource
from app.integrations.http.audit import DbAuditSink, SafeAuditSink
from app.integrations.http.client import ResilientHttpClient, create_http_client
from app.integrations.http.types import HostPolicy
from app.integrations.messaging.registry import create_messaging_channels
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

_DJEN_HOST = "comunicaapi.pje.jus.br"


async def _terms_to_sync(session: AsyncSession, term_id: uuid.UUID | None) -> list[MonitoredTerm]:
    """Quais termos esta execução varre.

    Com `term_id`, é a varredura sob demanda de UM termo — e só se ele estiver ativo:
    disparar à mão não contorna o desligamento feito pelo escritório.

    Sem ele, é a varredura agendada, e ela junta dois conjuntos: os que venceram o
    intervalo e os que ficaram com execução ABERTA. O segundo é o que faz uma varredura
    interrompida no meio (deploy, timeout) ser retomada em vez de esquecida — daí a
    deduplicação por id, que evita varrer duas vezes quem está nos dois.
    """
    repository = MonitoredTermRepository(session)
    if term_id is not None:
        term = await session.get(MonitoredTerm, term_id)
        return [term] if term is not None and term.is_active else []
    selected = list(await repository.list_due(datetime.now(UTC)))
    due_ids = {term.id for term in selected}
    return selected + [
        term for term in await repository.list_with_open_run() if term.id not in due_ids
    ]


def _djen_http_client(
    settings: Settings, redis: Redis, session_factory: async_sessionmaker[AsyncSession]
) -> ResilientHttpClient:
    """O cliente HTTP do DJEN, com a política de rate limit do host.

    Regra 8: o limite mora na camada 041, por host e global entre workers — a task não
    paraleliza por termo além disso. É por isso que a política vai no cliente e não no
    laço: quem segura a vazão é o token bucket no Redis, não a estrutura do worker.
    """
    return create_http_client(
        redis=redis,
        audit=SafeAuditSink(DbAuditSink(session_factory)),
        policies={
            _DJEN_HOST: HostPolicy(rate_limit_per_minute=settings.djen_rate_limit_per_minute)
        },
    )


async def run_due_syncs(term_id: uuid.UUID | None = None) -> dict[str, int]:
    """Executa a varredura. Recebe a infra de produção montada na hora (o worker
    roda fora do ciclo de request); devolve contadores para o resultado da task."""
    settings = get_settings()
    engine = create_engine_from_url(migrations_url("a varredura cross-tenant do DJEN"))
    session_factory = create_session_factory(engine)
    redis = create_redis_client()
    http = _djen_http_client(settings, redis, session_factory)
    try:
        source = DjenPublicationSource(
            DjenClient(
                http=http,
                base_url=settings.djen_base_url,
                user_agent=settings.djen_user_agent,
            )
        )
        lock = RedisSyncLock(redis)

        async with session_factory() as session, session.begin():
            selected = await _terms_to_sync(session, term_id)

        by_tenant: dict[uuid.UUID, list[MonitoredTerm]] = {}
        for term in selected:
            by_tenant.setdefault(term.tenant_id, []).append(term)

        channels = create_messaging_channels()
        ok = failed = 0
        for tenant_id, terms in by_tenant.items():
            async with session_factory() as session:
                service = TermSyncService(
                    session,
                    tenant_id,
                    source,
                    lock=lock,
                    lock_ttl_seconds=settings.djen_sync_lock_ttl_seconds,
                    cron=settings.djen_sync_cron,
                    channels=channels,
                )
                for run in await service.sync_terms(terms):
                    if run.error is None:
                        ok += 1
                    else:
                        failed += 1
        return {"terms": len(selected), "ok": ok, "failed": failed}
    finally:
        await http.aclose()
        await redis.aclose()
        await engine.dispose()


@celery_app.task(name="app.workers.djen_sync.sync_due_terms")
def sync_due_terms() -> dict[str, int]:
    return asyncio.run(run_due_syncs())


@celery_app.task(name="app.workers.djen_sync.sync_term_by_id")
def sync_term_by_id(term_id: str) -> dict[str, int]:
    return asyncio.run(run_due_syncs(uuid.UUID(term_id)))


def schedule_term_sync(term_id: uuid.UUID, countdown: float = 5.0) -> None:
    """Gatilho manual (regra 10 da 043): agenda o processamento da run recém-aberta.
    O countdown dá tempo do commit da request acontecer antes do worker ler; no
    ambiente de teste é no-op proposital (teste não toca broker — CLAUDE.md §3)."""
    if get_settings().app_env == "test":
        return
    try:
        celery_app.send_task(
            "app.workers.djen_sync.sync_term_by_id", args=[str(term_id)], countdown=countdown
        )
    except Exception:  # broker fora do ar não derruba a request — o beat diário cobre
        logger.warning("falha ao agendar sync do termo %s — o beat diário cobre.", term_id)
