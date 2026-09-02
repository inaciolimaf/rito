import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import decode_cursor, encode_cursor
from app.domain.locations.models import State
from app.domain.monitored_terms.exceptions import (
    BackfillTooOldError,
    InvalidTermStateError,
    SyncAlreadyRunningError,
    TermAlreadyExistsError,
)
from app.domain.monitored_terms.models import (
    MonitoredTerm,
    TermKind,
    TermStatus,
    TermSyncRun,
)
from app.domain.monitored_terms.repository import MonitoredTermRepository, TermSyncRunRepository
from app.domain.monitored_terms.schemas import (
    BACKFILL_DEFAULT_DAYS,
    BACKFILL_MAX_DAYS,
    MonitoredTermCreateRequest,
    MonitoredTermUpdateRequest,
)
from app.domain.users.models import User


class InvalidOabStateError(Exception):
    """UF da OAB não existe na tabela de estados (018)."""


class ResponsibleUserNotFoundError(Exception):
    """Regra 4: o responsável padrão precisa ser um usuário do tenant."""


class MonitoredTermService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.terms = MonitoredTermRepository(session)
        self.runs = TermSyncRunRepository(session)

    async def _validate_references(self, oab_state: str | None, user_id: uuid.UUID | None) -> None:
        if oab_state is not None and await self.session.get(State, oab_state) is None:
            raise InvalidOabStateError
        if user_id is not None and await self.session.get(User, user_id) is None:
            raise ResponsibleUserNotFoundError

    def _check_backfill(self, backfill_from: date | None, today: date) -> None:
        """Regra 6: captura inicial limitada a 12 meses, contados no fuso do escritório."""
        if backfill_from is not None and backfill_from < today - timedelta(days=BACKFILL_MAX_DAYS):
            raise BackfillTooOldError

    async def create(self, payload: MonitoredTermCreateRequest, today: date) -> MonitoredTerm:
        self._check_backfill(payload.backfill_from, today)
        await self._validate_references(payload.oab_state, payload.user_id)
        if (
            await self.terms.find_duplicate(
                kind=payload.kind, value=payload.value, oab_state=payload.oab_state
            )
            is not None
        ):
            raise TermAlreadyExistsError

        now = datetime.now(UTC)
        term = MonitoredTerm(
            tenant_id=self.tenant_id,
            kind=payload.kind,
            value=payload.value,
            oab_state=payload.oab_state,
            label=payload.label,
            user_id=payload.user_id,
            status=TermStatus.PENDENTE,  # regra 5
            backfill_from=payload.backfill_from or (today - timedelta(days=BACKFILL_DEFAULT_DAYS)),
            next_sync_at=now,  # nasce devendo a primeira sincronização
        )
        await self.terms.create(term)
        return term

    async def update(
        self, term: MonitoredTerm, payload: MonitoredTermUpdateRequest, today: date
    ) -> MonitoredTerm:
        self._check_backfill(payload.backfill_from, today)
        await self._validate_references(None, payload.user_id)
        # kind/value/oab_state são imutáveis — trocar o termo é excluir e recriar.
        term.label = payload.label
        term.user_id = payload.user_id
        term.backfill_from = payload.backfill_from
        term.is_active = payload.is_active
        await self.session.flush()
        return term

    async def delete(self, term: MonitoredTerm) -> None:
        # Regra 8: publications não referenciam o termo — as capturadas ficam.
        await self.terms.delete(term)
        await self.session.flush()

    async def pause(self, term: MonitoredTerm) -> MonitoredTerm:
        if term.status is TermStatus.PAUSADO:
            raise InvalidTermStateError
        term.status = TermStatus.PAUSADO  # regra 7: sai do agendamento, histórico fica
        await self.session.flush()
        return term

    async def resume(self, term: MonitoredTerm) -> MonitoredTerm:
        if term.status is not TermStatus.PAUSADO:
            raise InvalidTermStateError
        term.status = TermStatus.ATIVO if term.last_success_at else TermStatus.PENDENTE
        term.next_sync_at = datetime.now(UTC)
        await self.session.flush()
        return term

    async def start_manual_sync(self, term: MonitoredTerm) -> TermSyncRun:
        """Regra 10: abre a execução (o processamento em si é da spec 044); se já
        houver uma em andamento, 409."""
        if await self.runs.get_running(term.id) is not None:
            raise SyncAlreadyRunningError
        run = TermSyncRun(tenant_id=self.tenant_id, term_id=term.id)
        await self.runs.create(run)
        term.status = TermStatus.SINCRONIZANDO
        await self.session.flush()
        return run

    async def list_terms(
        self, *, status: TermStatus | None, kind: TermKind | None, query: str | None
    ) -> Sequence[MonitoredTerm]:
        return await self.terms.list_filtered(status=status, kind=kind, query=query)

    async def captured_counts(self, term_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        """ "Capturadas" da listagem: soma dos new_count das execuções do termo —
        publications não guardam vínculo com o termo (o casamento é por valor, 045)."""
        if not term_ids:
            return {}
        result = await self.session.execute(
            select(TermSyncRun.term_id, func.coalesce(func.sum(TermSyncRun.new_count), 0))
            .where(TermSyncRun.term_id.in_(term_ids))
            .group_by(TermSyncRun.term_id)
        )
        return {row[0]: int(row[1]) for row in result.all()}

    async def list_runs(
        self, term_id: uuid.UUID, *, cursor: str | None, limit: int
    ) -> tuple[Sequence[TermSyncRun], str | None, int]:
        decoded = decode_cursor(cursor) if cursor else None
        rows = list(await self.runs.list_for_term(term_id, cursor=decoded, limit=limit))
        total = await self.runs.count_for_term(term_id)
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            last = rows[-1]
            next_cursor = encode_cursor(last.started_at.isoformat(), last.id)
        return rows, next_cursor, total
