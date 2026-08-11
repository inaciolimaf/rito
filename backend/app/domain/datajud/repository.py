"""Histórico de execução do DataJud (spec 050, alvo 1) — mesma tabela `sync_runs`
do DJEN (spec 043), lado `lawsuit_id`/`integration='datajud'`. Repositório
próprio (não em `monitored_terms`) porque o assunto aqui é processo, não
termo — mesmo modelo, dono diferente (SRP)."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.monitored_terms.models import TermSyncRun


class LawsuitSyncRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, run: TermSyncRun) -> TermSyncRun:
        self.session.add(run)
        await self.session.flush()
        return run

    async def list_for_lawsuit(
        self, lawsuit_id: uuid.UUID, *, limit: int = 20
    ) -> Sequence[TermSyncRun]:
        stmt = (
            select(TermSyncRun)
            .where(TermSyncRun.lawsuit_id == lawsuit_id)
            .order_by(TermSyncRun.started_at.desc())
            .limit(limit)
        )
        return (await self.session.scalars(stmt)).all()
