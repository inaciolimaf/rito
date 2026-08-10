"""Sincronização de termos monitorados com o DJEN (spec 044).

Unidade de trabalho: um termo. O service percorre a janela incremental em
fatias de até 90 dias, pagina a fonte, deduplica por hash, trata anulações e
fecha a `TermSyncRun` com os contadores. Cada página é um commit — uma falha
no meio nunca deixa página pela metade (regra 9) e reprocessar é inócuo
(regra 1). O service NUNCA levanta exceção de negócio: falha vira `FALHA` no
termo com a mensagem (regra 6) e os demais termos seguem (regra 5).

A fonte é injetada (`PublicationSource`) — o DJEN é uma implementação
(app/integrations/djen/source.py) e o teste usa fakes sobre as fixtures
gravadas. Nenhuma chamada de rede mora aqui.

Detalhe de RLS: como o service commita por página, ele próprio rearma
`app.tenant_id` após cada commit/rollback — `set_config(..., is_local=true)`
vale só até o fim da transação, e sem o contexto o RLS esconderia as linhas
(e os UPDATEs afetariam 0 linhas em silêncio).
"""

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.locks import SyncLock
from app.core.rls import set_tenant_context
from app.domain.monitored_terms.models import MonitoredTerm, TermStatus, TermSyncRun
from app.domain.monitored_terms.repository import (
    MonitoredTermRepository,
    TermSyncRunRepository,
)
from app.domain.monitored_terms.schemas import BACKFILL_DEFAULT_DAYS
from app.domain.publications.repository import PublicationRepository
from app.domain.publications.service import PublicationService
from app.integrations.djen.parser import ParsedCommunication

logger = logging.getLogger("rito.djen_sync")

MAX_WINDOW_DAYS = 90  # regra 12: fatia máxima por execução
WINDOW_OVERLAP_DAYS = 1  # regra 3: cobre publicação que entra atrasada no DJEN
ITEMS_PER_PAGE = 100  # regra 9 da spec 042: teto da API, protege o rate limit
_STATUS_MESSAGE_MAX = 500


@dataclass
class PublicationPage:
    count: int
    items: list[ParsedCommunication]


class PublicationSource(Protocol):
    """Fonte de publicações (spec 044, §6). O DJEN é uma implementação; trocar
    a fonte não toca neste service (OCP)."""

    async def fetch(
        self, *, term: MonitoredTerm, start: date, end: date, page: int
    ) -> PublicationPage: ...


def next_daily_run(cron: str, after: datetime) -> datetime:
    """Próxima ocorrência de um cron **diário** ("m h * * *") após `after`.

    O beat aceita os 5 campos do crontab; o cálculo de `next_sync_at` (regra 9
    da 043) só sabe avançar um dia — daí a exigência de forma diária, validada
    aqui e no boot do celery_app (falhar cedo, não agendar errado em silêncio).
    """
    parts = cron.split()
    if len(parts) != 5 or parts[2] != "*" or parts[3] != "*" or parts[4] != "*":
        raise ValueError(f"DJEN_SYNC_CRON precisa ser diário ('m h * * *'), recebido: {cron!r}")
    minute, hour = int(parts[0]), int(parts[1])
    candidate = after.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= after:
        candidate += timedelta(days=1)
    return candidate


def _is_cancellation(parsed: ParsedCommunication) -> bool:
    """Regra 2: anulação chega como `ativo=false` ou `motivo_cancelamento`."""
    return not parsed.is_active or parsed.cancellation_reason is not None


class TermSyncService:
    def __init__(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        source: PublicationSource,
        *,
        lock: SyncLock | None = None,
        lock_ttl_seconds: int = 3600,
        cron: str = "17 3 * * *",
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.source = source
        self.lock = lock
        self.lock_ttl_seconds = lock_ttl_seconds
        self.cron = cron
        self.terms = MonitoredTermRepository(session)
        self.runs = TermSyncRunRepository(session)
        self.publications = PublicationRepository(session)
        self.publication_service = PublicationService(session=session, tenant_id=tenant_id)

    async def _commit(self) -> None:
        await self.session.commit()
        # SET LOCAL morre no commit — sem rearmar, o RLS esconde tudo na
        # transação seguinte (multi-tenancy, CLAUDE.md §4).
        await set_tenant_context(self.session, self.tenant_id)

    async def _rollback(self) -> None:
        await self.session.rollback()
        await set_tenant_context(self.session, self.tenant_id)

    async def sync_terms(
        self, terms: Sequence[MonitoredTerm], *, now: datetime | None = None
    ) -> list[TermSyncRun]:
        """Regra 5: cada termo é uma unidade isolada — falha em um não interrompe
        os demais, nem no caminho tratado (FALHA) nem num erro inesperado."""
        finished: list[TermSyncRun] = []
        for term in terms:
            try:
                run = await self.sync_term(term, now=now)
            except Exception:
                logger.exception("djen_sync: falha inesperada no termo %s", term.id)
                await self._rollback()
                continue
            if run is not None:
                finished.append(run)
        return finished

    async def sync_term(
        self, term: MonitoredTerm, *, now: datetime | None = None
    ) -> TermSyncRun | None:
        """Sincroniza um termo. Devolve a run fechada, ou None quando outra
        execução do mesmo termo segura o lock (regra 10) — desistir é o
        comportamento certo: a execução concorrente já está fazendo o trabalho."""
        now = now or datetime.now(UTC)
        acquired = False
        if self.lock is not None:
            acquired = await self.lock.acquire(
                f"rito:djen_sync:{term.id}", ttl_seconds=self.lock_ttl_seconds
            )
            if not acquired:
                return None
        try:
            await set_tenant_context(self.session, self.tenant_id)
            # O objeto pode vir de outra sessão (a listagem cross-tenant do
            # worker) — recarrega na sessão do service antes de qualquer acesso.
            attached = await self.terms.get_by_id(term.id)
            if attached is None:
                return None  # termo apagado entre a listagem e a execução
            return await self._execute(attached, now)
        finally:
            if acquired and self.lock is not None:
                await self.lock.release(f"rito:djen_sync:{term.id}")

    async def _execute(self, term: MonitoredTerm, now: datetime) -> TermSyncRun:
        # Sync manual da 043 abre a run sem processar — a varredura consome a
        # run aberta em vez de criar outra (descoberta registrada na spec 043).
        run = await self.runs.get_running(term.id)
        if run is None:
            run = TermSyncRun(tenant_id=self.tenant_id, term_id=term.id, started_at=now)
            await self.runs.create(run)
        term.status = TermStatus.SINCRONIZANDO
        term.last_sync_at = now
        await self._commit()

        try:
            today = now.date()
            start = self._window_start(term, today)
            while start <= today:
                end = min(start + timedelta(days=MAX_WINDOW_DAYS), today)
                await self._sync_window(term, run, start, end)
                term.last_captured_date = end
                await self._commit()
                start = end + timedelta(days=1)
        except Exception as exc:
            # Regra 9: rollback descarta a página em andamento — as páginas já
            # commitadas ficam e o re-run não as duplica (regra 1).
            await self._rollback()
            message = str(exc)[:_STATUS_MESSAGE_MAX]
            run.error = message
            run.finished_at = now
            term.status = TermStatus.FALHA  # regra 6
            term.status_message = message
            term.next_sync_at = next_daily_run(self.cron, now)
            await self._commit()
            return run

        run.finished_at = now
        term.status = TermStatus.ATIVO
        term.status_message = None
        term.last_success_at = now  # regra 11: silêncio é resultado válido
        term.next_sync_at = next_daily_run(self.cron, now)
        await self._commit()
        return run

    @staticmethod
    def _window_start(term: MonitoredTerm, today: date) -> date:
        """Regras 3 e 4: incremental a partir de last_captured_date com 1 dia de
        sobreposição; primeira execução usa backfill_from."""
        if term.last_captured_date is not None:
            return term.last_captured_date - timedelta(days=WINDOW_OVERLAP_DAYS)
        backfill = term.backfill_from or (today - timedelta(days=BACKFILL_DEFAULT_DAYS))
        return min(backfill, today)

    async def _sync_window(
        self, term: MonitoredTerm, run: TermSyncRun, start: date, end: date
    ) -> None:
        page = 1
        while True:
            result = await self.source.fetch(term=term, start=start, end=end, page=page)
            if not result.items:
                break
            for parsed in result.items:
                run.found_count += 1
                if await self._process_item(parsed):
                    run.new_count += 1
            await self._commit()  # regra 9: a página é a unidade transacional
            if len(result.items) < ITEMS_PER_PAGE or page * ITEMS_PER_PAGE >= result.count:
                break
            page += 1

    async def _process_item(self, parsed: ParsedCommunication) -> bool:
        """Persiste o item. Devolve True quando era publicação nova (o contador
        new_count da run só conta inserção — dedup e anulação não)."""
        existing = await self.publications.get_by_hash(parsed.hash)
        if existing is None:
            await self.publication_service.register(parsed)  # regra 1: hash é a chave
            return True
        if _is_cancellation(parsed) and existing.is_active:
            # Regra 2: anulação marca, nunca apaga — a linha fica com motivo e data.
            existing.is_active = False
            existing.cancellation_reason = parsed.cancellation_reason
            existing.cancelled_at = parsed.cancelled_at
            existing.status = parsed.status
        return False
