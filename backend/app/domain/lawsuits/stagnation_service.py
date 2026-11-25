"""Estagnação do CRM (spec 052) — cálculo derivado, sem estado histórico.

`is_stagnant`/`stagnant_since` são recalculados do zero a cada chamada: como as
duas dependem só de `stage_entered_at` (regra 1) e `stagnant_days` da etapa atual
(regra 5 — "guarda quando entrou em estagnação"), não há necessidade de preservar
o valor anterior. `stagnant_since` é a data exata em que o processo cruzou o
limite (`stage_entered_at + stagnant_days`), não "hoje" — é isso que dá a ordenação
por gravidade (regra 5) sem uma coluna extra.

Recalcula por etapa em 1 UPDATE (regra 10: "mudar `stagnant_days` recalcula a
etapa"); `recalculate_tenant` soma o de todas as etapas do tenant (regra 4: job
diário / gatilho manual). Mover processo NÃO passa por aqui — `BoardService.
change_stage` zera `is_stagnant`/`stagnant_since` direto (regra 4: 0 dias na etapa
nova nunca é estagnação, não vale gastar uma query nisso).
"""

import uuid

from sqlalchemy import Date, and_, case, cast, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.sql import days_interval
from app.domain.lawsuits.models import Lawsuit
from app.domain.stages.models import Stage
from app.domain.stages.repository import StageRepository


class StagnationService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.stages = StageRepository(session)

    async def recalculate_stage(self, stage: Stage) -> int:
        """1 UPDATE — regra 2: etapa sem `enable_stagnant_days` nunca marca."""
        if not stage.enable_stagnant_days or not stage.stagnant_days:
            stmt = (
                update(Lawsuit)
                .where(Lawsuit.stage_id == stage.id)
                .values(is_stagnant=False, stagnant_since=None)
            )
        else:
            # `make_interval` com o número LIGADO (spec 127): evita a coerção de tipo
            # ambígua do SQLAlchemy ao somar/subtrair um `timedelta` de uma coluna
            # Date/DateTime — que era o motivo do `text()` — sem montar SQL por string.
            # Mesmo helper de `_idle()` em listing.py.
            interval = days_interval(stage.stagnant_days)
            is_stagnant_expr = and_(
                Lawsuit.is_archived.is_(False),  # regra 6
                func.now() - Lawsuit.stage_entered_at > interval,  # regra 1/3
            )
            stmt = (
                update(Lawsuit)
                .where(Lawsuit.stage_id == stage.id)
                .values(
                    is_stagnant=is_stagnant_expr,
                    # Regra 5: a data em que cruzou o limite, não "hoje".
                    stagnant_since=case(
                        (is_stagnant_expr, cast(Lawsuit.stage_entered_at + interval, Date)),
                        else_=None,
                    ),
                )
            )
        result = await self.session.execute(stmt)
        return int(result.rowcount)  # type: ignore[attr-defined]  # SQLAlchemy tipa `rowcount` só em `CursorResult`; um UPDATE/DELETE sempre devolve um.

    async def recalculate_tenant(self) -> int:
        stages = await self.stages.list_filtered()
        total = 0
        for stage in stages:
            total += await self.recalculate_stage(stage)
        return total
