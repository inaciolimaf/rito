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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock
from app.core.locks import SyncLock
from app.core.observability.metrics import record_sync_run
from app.core.rls import set_tenant_context
from app.domain.account.repository import AccountRepository
from app.domain.integration_alerts.models import IntegrationAlert
from app.domain.integration_alerts.repository import IntegrationAlertRepository
from app.domain.monitored_terms.models import MonitoredTerm, TermStatus, TermSyncRun
from app.domain.monitored_terms.repository import (
    MonitoredTermRepository,
    TermSyncRunRepository,
)
from app.domain.monitored_terms.schemas import BACKFILL_DEFAULT_DAYS
from app.domain.publications.repository import PublicationRepository
from app.domain.publications.routing import PublicationRoutingService
from app.domain.publications.service import PublicationService
from app.domain.users.repository import UserRepository
from app.integrations.djen.parser import ParsedCommunication
from app.integrations.messaging.base import MessagingChannel

logger = logging.getLogger("rito.djen_sync")

MAX_WINDOW_DAYS = 90  # regra 12: fatia máxima por execução
WINDOW_OVERLAP_DAYS = 1  # regra 3: cobre publicação que entra atrasada no DJEN
ITEMS_PER_PAGE = 100  # regra 9 da spec 042: teto da API, protege o rate limit
_STATUS_MESSAGE_MAX = 500
CONSECUTIVE_FAILURE_ALERT_THRESHOLD = 3  # spec 049, regra 1


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


def _append_note(existing: str, note: str) -> str:
    return f"{existing}\n\n{note}"


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
        channels: Mapping[str, MessagingChannel] | None = None,
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
        self.routing = PublicationRoutingService(
            session=session, tenant_id=tenant_id, channels=channels
        )
        self.alerts = IntegrationAlertRepository(session)
        self.users = UserRepository(session)

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

    async def _open_run(self, term: MonitoredTerm, now: datetime) -> TermSyncRun:
        """A execução desta varredura — a aberta que já existia, ou uma nova.

        Sync manual da 043 abre a run sem processar, e a varredura agendada CONSOME essa
        run em vez de criar outra: sem isso, pedir sync à mão e deixar o agendador rodar
        em seguida produziria duas execuções para o mesmo trabalho.
        """
        run = await self.runs.get_running(term.id)
        if run is None:
            run = TermSyncRun(tenant_id=self.tenant_id, term_id=term.id, started_at=now)
            await self.runs.create(run)
        term.status = TermStatus.SINCRONIZANDO
        term.last_sync_at = now
        await self._commit()
        return run

    async def _sync_windows(self, term: MonitoredTerm, run: TermSyncRun, now: datetime) -> None:
        """Varre do último dia capturado até hoje, em janelas de `MAX_WINDOW_DAYS`.

        Spec 114, regra 3: a janela é em dias do ESCRITÓRIO, não em dias UTC. `now`
        continua sendo o instante (carimbo de `started_at`/`last_sync_at`, e a costura por
        onde os testes de caos injetam relógio torto); o que muda é em que fuso esse
        instante vira «dia». Com `now.date()`, a partir das 21h de Brasília o Rito pedia ao
        DJEN as publicações de AMANHÃ. O `DTZ` não pega este caso: `datetime.now(UTC)` tem
        fuso, só que o fuso errado para a pergunta.

        Cada janela comita: interrupção no meio deixa o que já entrou (regra 1) e o
        `last_captured_date` diz por onde retomar.
        """
        fuso = Clock(await AccountRepository(self.session).timezone()).timezone
        today = now.astimezone(fuso).date()
        start = self._window_start(term, today)
        while start <= today:
            end = min(start + timedelta(days=MAX_WINDOW_DAYS), today)
            await self._sync_window(term, run, start, end)
            term.last_captured_date = end
            await self._commit()
            start = end + timedelta(days=1)

    async def _mark_failed(
        self, term: MonitoredTerm, run: TermSyncRun, exc: Exception, now: datetime
    ) -> None:
        """Registra a falha no termo e na run, e escala se já vem falhando (spec 049).

        O contador de falhas CONSECUTIVAS é o que separa uma indisponibilidade momentânea do
        DJEN de um termo realmente quebrado: alertar na primeira falha encheria a caixa do
        escritório de ruído, e nunca alertar deixaria um termo parado por semanas.
        """
        message = str(exc)[:_STATUS_MESSAGE_MAX]
        run.error = message
        run.finished_at = now
        term.status = TermStatus.FALHA  # regra 6
        term.status_message = message
        term.next_sync_at = next_daily_run(self.cron, now)
        term.consecutive_failures += 1  # spec 049, regra 1
        record_sync_run(integration="djen", status="error")  # spec 097, regra 6
        if term.consecutive_failures >= CONSECUTIVE_FAILURE_ALERT_THRESHOLD:
            await self._raise_or_update_alert(term, message)

    async def _mark_succeeded(self, term: MonitoredTerm, run: TermSyncRun, now: datetime) -> None:
        """Fecha a run com sucesso e zera o histórico de falhas.

        Regra 11: SILÊNCIO É RESULTADO VÁLIDO — uma varredura que não encontrou nenhuma
        intimação é sucesso, e `last_success_at` marca isso. Sem essa distinção, um termo
        legítimo sem movimento seria indistinguível de um termo que parou de funcionar.
        """
        if term.consecutive_failures > 0 or term.alert_id is not None:
            await self._resolve_alert(term, now)  # spec 049, regra 3
        run.finished_at = now
        term.status = TermStatus.ATIVO
        term.status_message = None
        term.last_success_at = now
        record_sync_run(integration="djen", status="ok")  # spec 097, regra 6
        term.next_sync_at = next_daily_run(self.cron, now)
        term.consecutive_failures = 0

    async def _execute(self, term: MonitoredTerm, now: datetime) -> TermSyncRun:
        # Sync manual da 043 abre a run sem processar — a varredura consome a
        # run aberta em vez de criar outra (descoberta registrada na spec 043).
        run = await self._open_run(term, now)
        try:
            await self._sync_windows(term, run, now)
        except Exception as exc:
            # Regra 9: rollback descarta a página em andamento — as páginas já
            # commitadas ficam e o re-run não as duplica (regra 1). O rollback
            # expira os atributos do objeto — refresh() explícito porque a sessão
            # é assíncrona e não faz lazy-load implícito (levantaria MissingGreenlet
            # no primeiro acesso a um atributo não tocado, como term.user_id/alert_id
            # logo abaixo, spec 049).
            await self._rollback()
            await self.session.refresh(term)
            await self._mark_failed(term, run, exc, now)
            await self._commit()
            return run

        await self._mark_succeeded(term, run, now)
        await self._commit()
        return run

    async def _raise_or_update_alert(self, term: MonitoredTerm, message: str) -> None:
        """Spec 049, regras 1-2: alerta é um só por termo — nova falha atualiza a
        mensagem do alerta aberto em vez de criar outro."""
        if term.alert_id is not None:
            alert = await self.alerts.get_by_id(term.alert_id)
            if alert is not None and alert.resolved_at is None:
                alert.message = _append_note(alert.message, f"Nova falha: {message}")
                return
        responsible_id = term.user_id
        if responsible_id is None:
            gestor = await self.users.get_oldest_active_gestor()
            responsible_id = gestor.id if gestor is not None else None
        alert = IntegrationAlert(
            tenant_id=self.tenant_id,
            integration="djen",
            severity="warning",
            code="term_sync_failed",
            message=(
                f"O termo {term.value} falhou {term.consecutive_failures} vezes seguidas "
                f"na sincronização: {message}"
            ),
            responsible_user_id=responsible_id,
        )
        await self.alerts.create(alert)
        term.alert_id = alert.id

    async def _resolve_alert(self, term: MonitoredTerm, now: datetime) -> None:
        """Spec 049, regra 3: sucesso resolve o alerta aberto e anota a normalização."""
        if term.alert_id is None:
            return
        alert = await self.alerts.get_by_id(term.alert_id)
        if alert is not None and alert.resolved_at is None:
            alert.message = _append_note(
                alert.message,
                f"Normalizado em {now.isoformat()} — sincronização voltou a funcionar.",
            )
            alert.resolved_at = now
        term.alert_id = None

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
            registered = await self.publication_service.register(parsed)  # regra 1: hash é a chave
            # Spec 045: toda publicação nova passa pelo roteamento — o casamento decide
            # se vira tarefa; sem processo casado, ela só fica marcada como processada.
            await self.routing.route(registered)
            return True
        if _is_cancellation(parsed) and existing.is_active:
            # Regra 2: anulação marca, nunca apaga — a linha fica com motivo e data.
            existing.is_active = False
            existing.cancellation_reason = parsed.cancellation_reason
            existing.cancelled_at = parsed.cancelled_at
            existing.status = parsed.status
            await self.routing.handle_cancellation(existing)  # regra 8 da spec 045
        return False
