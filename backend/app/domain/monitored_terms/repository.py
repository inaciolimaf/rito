import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, literal, or_, select, tuple_

from app.core.repository import BaseRepository
from app.domain.monitored_terms.models import MonitoredTerm, TermKind, TermStatus, TermSyncRun


class MonitoredTermRepository(BaseRepository[MonitoredTerm]):
    model = MonitoredTerm

    async def find_duplicate(
        self, *, kind: TermKind, value: str, oab_state: str | None
    ) -> MonitoredTerm | None:
        stmt = select(MonitoredTerm).where(
            MonitoredTerm.kind == kind,
            MonitoredTerm.value == value,
            MonitoredTerm.oab_state.is_not_distinct_from(oab_state),
        )
        result = await self.session.scalars(stmt)
        return result.first()

    async def list_filtered(
        self, *, status: TermStatus | None, kind: TermKind | None, query: str | None
    ) -> Sequence[MonitoredTerm]:
        stmt = select(MonitoredTerm).order_by(MonitoredTerm.created_at.desc())
        if status is not None:
            stmt = stmt.where(MonitoredTerm.status == status)
        if kind is not None:
            stmt = stmt.where(MonitoredTerm.kind == kind)
        if query:
            stmt = stmt.where(
                or_(
                    MonitoredTerm.value.ilike(f"%{query}%"),
                    MonitoredTerm.label.ilike(f"%{query}%"),
                )
            )
        result = await self.session.scalars(stmt)
        return result.all()

    async def list_due(self, now: datetime) -> Sequence[MonitoredTerm]:
        """Termos prontos para sincronizar (regra 7: pausado/inativo fica de fora —
        o mesmo predicado do índice parcial ix_terms_due)."""
        stmt = (
            select(MonitoredTerm)
            .where(
                MonitoredTerm.is_active.is_(True),
                MonitoredTerm.status != TermStatus.PAUSADO,
                MonitoredTerm.next_sync_at <= now,
            )
            .order_by(MonitoredTerm.next_sync_at)
        )
        result = await self.session.scalars(stmt)
        return result.all()

    async def list_with_open_run(self) -> Sequence[MonitoredTerm]:
        """Termos com execução aberta (sync manual da 043) — a varredura da 044
        consome essas runs além dos termos devidos. Mesmo predicado do
        ix_terms_due: pausado/inativo fica de fora."""
        stmt = (
            select(MonitoredTerm)
            .join(TermSyncRun, TermSyncRun.term_id == MonitoredTerm.id)
            .where(
                MonitoredTerm.is_active.is_(True),
                MonitoredTerm.status != TermStatus.PAUSADO,
                TermSyncRun.finished_at.is_(None),
            )
            .order_by(MonitoredTerm.next_sync_at)
        )
        result = await self.session.scalars(stmt)
        return result.all()


class TermSyncRunRepository(BaseRepository[TermSyncRun]):
    model = TermSyncRun

    async def get_running(self, term_id: uuid.UUID) -> TermSyncRun | None:
        """Execução em andamento do termo (finished_at nulo) — trava da regra 10."""
        result = await self.session.scalars(
            select(TermSyncRun).where(
                TermSyncRun.term_id == term_id, TermSyncRun.finished_at.is_(None)
            )
        )
        return result.first()

    async def list_for_term(
        self,
        term_id: uuid.UUID,
        *,
        cursor: tuple[str, uuid.UUID] | None,
        limit: int,
    ) -> Sequence[TermSyncRun]:
        """Keyset por (started_at, id) desc — contrato de listagem do CLAUDE.md §6."""
        stmt = (
            select(TermSyncRun)
            .where(TermSyncRun.term_id == term_id)
            .order_by(TermSyncRun.started_at.desc(), TermSyncRun.id.desc())
            .limit(limit + 1)
        )
        if cursor is not None:
            cursor_value, cursor_id = cursor
            # literal(): mesmo motivo anotado em core.repository.build_sorted_keyset_query.
            stmt = stmt.where(
                tuple_(TermSyncRun.started_at, TermSyncRun.id)
                < tuple_(literal(cursor_value), literal(cursor_id))
            )
        result = await self.session.scalars(stmt)
        return result.all()

    async def count_for_term(self, term_id: uuid.UUID) -> int:
        total = await self.session.scalar(
            select(func.count()).select_from(TermSyncRun).where(TermSyncRun.term_id == term_id)
        )
        return total or 0
