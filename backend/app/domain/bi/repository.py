"""Agregações do BI de Estoque e Prospecção (spec 074).

Dois mundos, como manda a regra 8:

- **view barreira `bi_pipeline_monthly`** (matview, até 8 h de defasagem): oportunidades
  da coorte e o funil de conversão por grupo de ação;
- **tempo real sobre `lawsuits`**: estoque (ativos, parados +120, em atendimento,
  arquivados), fechamentos por `closure_date` e o resumo da carteira do rodapé.

Nenhuma query filtra tenant no WHERE: lawsuits/stages/action_groups/lawsuit_types têm
RLS e a view barreira embute o filtro na definição (migration 074).
"""

import uuid
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import ColumnElement, Date, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.action_groups.models import ActionGroup, LawsuitType
from app.domain.bi.models import (
    ConversionGroupRow,
    CycleGroupRow,
    LostTimeRow,
    PortfolioPeriodRow,
    PortfolioStepRow,
    ProfitabilityTypeRow,
    StockCounts,
    SuccessGroupRow,
    SuccessMonthRow,
    TimeFeesAggregateRow,
    VintageYearRow,
    bi_lawsuit_cycles,
    bi_pipeline_monthly,
    bi_vintage,
)
from app.domain.lawsuits.models import Lawsuit, LawsuitOutcome
from app.domain.stages.models import Stage, Step

# Fases fixas do seed da migration 015 (ids sequenciais na ordem de `position`) — mesma
# convenção dos testes (`_MARKETING_STEP_ID = 1` em test_lawsuits.py): 1 Marketing,
# 2 Negociação, 3 Consultoria, 4 Administrativo, 5 Judicial, 6 Recursal,
# 7 Execução/cobrança, 8 Rh/financeiro, 9 Arquivamento.
# Regra 2 (ativos) e regra 6 (em atendimento) — Consultoria entra nos dois conjuntos.
ACTIVE_STEP_IDS = (3, 4, 5, 6, 7)
IN_SERVICE_STEP_IDS = (1, 2, 3)


class BiPipelineRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---- view materializada (coorte por mês de criação) --------------------------

    async def opportunities(
        self, *, month_start: date, month_end: date, action_group_id: uuid.UUID | None
    ) -> int:
        """Regra 1: processos criados nos meses da janela, qualquer fase — da view."""
        conditions = [
            bi_pipeline_monthly.c.month >= month_start,
            bi_pipeline_monthly.c.month <= month_end,
        ]
        if action_group_id is not None:
            conditions.append(bi_pipeline_monthly.c.action_group_id == action_group_id)
        stmt = select(func.coalesce(func.sum(bi_pipeline_monthly.c.opportunities), 0)).where(
            *conditions
        )
        return int(await self.session.scalar(stmt) or 0)

    async def conversion_by_group(self, *, period: date) -> Sequence[ConversionGroupRow]:
        """Regras 7 e 10: TODOS os grupos ativos aparecem — quem não tem movimento no
        período vem zerado (LEFT JOIN), nunca some."""
        stmt = (
            select(
                ActionGroup.id,
                ActionGroup.name,
                func.coalesce(bi_pipeline_monthly.c.opportunities, 0),
                func.coalesce(bi_pipeline_monthly.c.closed, 0),
            )
            .outerjoin(
                bi_pipeline_monthly,
                and_(
                    bi_pipeline_monthly.c.action_group_id == ActionGroup.id,
                    bi_pipeline_monthly.c.month == period,
                ),
            )
            .where(ActionGroup.is_active.is_(True))
            .order_by(ActionGroup.name)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            ConversionGroupRow(
                action_group_id=group_id,
                action_group_name=name,
                opportunities=int(opportunities),
                closed=int(closed),
            )
            for group_id, name, opportunities, closed in rows
        ]

    # ---- tempo real sobre lawsuits ------------------------------------------------

    def _group_filter(self, action_group_id: uuid.UUID | None) -> list[ColumnElement[bool]]:
        return [LawsuitType.action_group_id == action_group_id] if action_group_id else []

    async def stock_counts(
        self, *, idle_cutoff: datetime, action_group_id: uuid.UUID | None
    ) -> StockCounts:
        """Uma query com os 4 agregados de estoque (regras 2, 3, 4 e 6).

        Base de estoque = não arquivado e sem `archived_date` (mesmo idioma da visão
        `active` da listagem, spec 027: quem tem data de arquivamento é fato processual,
        independente da flag)."""
        stock_base = and_(Lawsuit.is_archived.is_(False), Lawsuit.archived_date.is_(None))
        active_base = and_(stock_base, Stage.step_id.in_(ACTIVE_STEP_IDS))
        idle_condition = and_(
            active_base,
            or_(
                Lawsuit.last_movement_at.is_(None),
                Lawsuit.last_movement_at < idle_cutoff,
            ),
        )
        stmt = (
            select(
                func.count().filter(active_base).label("active"),
                func.count().filter(Lawsuit.archived_date.is_not(None)).label("archived"),
                func.count().filter(idle_condition).label("idle_120"),
                func.count()
                .filter(and_(stock_base, Stage.step_id.in_(IN_SERVICE_STEP_IDS)))
                .label("in_service"),
            )
            .select_from(Lawsuit)
            .join(Stage, Stage.id == Lawsuit.stage_id)
            .join(LawsuitType, LawsuitType.id == Lawsuit.lawsuit_type_id)
            .where(*self._group_filter(action_group_id))
        )
        row = (await self.session.execute(stmt)).one()
        return StockCounts(
            active=int(row.active),
            archived=int(row.archived),
            idle_120=int(row.idle_120),
            in_service=int(row.in_service),
        )

    async def closed_counts(
        self,
        *,
        start: date,
        end: date,
        previous_start: date,
        previous_end: date,
        action_group_id: uuid.UUID | None,
    ) -> tuple[int, int]:
        """Regra 5: fechamentos do período e do período anterior (por `closure_date`,
        tempo real — a view é coorte de criação e não responde isto, ver §9 da spec)."""
        stmt = (
            select(
                func.count()
                .filter(and_(Lawsuit.closure_date >= start, Lawsuit.closure_date <= end))
                .label("closed"),
                func.count()
                .filter(
                    and_(
                        Lawsuit.closure_date >= previous_start,
                        Lawsuit.closure_date <= previous_end,
                    )
                )
                .label("closed_prev"),
            )
            .select_from(Lawsuit)
            .join(LawsuitType, LawsuitType.id == Lawsuit.lawsuit_type_id)
            .where(*self._group_filter(action_group_id))
        )
        row = (await self.session.execute(stmt)).one()
        return int(row.closed), int(row.closed_prev)

    async def closed_trend(
        self, *, first_month: date, action_group_id: uuid.UUID | None
    ) -> dict[date, int]:
        """Série de fechamentos por mês (regra 5) — o service completa os meses zerados."""
        month_expr = func.date_trunc("month", Lawsuit.closure_date).cast(Date)
        stmt = (
            select(month_expr, func.count())
            .select_from(Lawsuit)
            .join(LawsuitType, LawsuitType.id == Lawsuit.lawsuit_type_id)
            .where(Lawsuit.closure_date >= first_month, *self._group_filter(action_group_id))
            .group_by(month_expr)
        )
        rows = (await self.session.execute(stmt)).all()
        return {month: int(count) for month, count in rows}

    async def portfolio_by_step(
        self, *, action_group_id: uuid.UUID | None
    ) -> Sequence[PortfolioStepRow]:
        """Resumo da carteira por fase (tempo real): as 9 fases aparecem sempre, mesmo
        zeradas — carteira = não arquivados e sem `archived_date`, qualquer fase."""
        lawsuit_join = and_(
            Lawsuit.stage_id == Stage.id,
            Lawsuit.is_archived.is_(False),
            Lawsuit.archived_date.is_(None),
        )
        if action_group_id is not None:
            lawsuit_join = and_(
                lawsuit_join,
                Lawsuit.lawsuit_type_id.in_(
                    select(LawsuitType.id).where(LawsuitType.action_group_id == action_group_id)
                ),
            )
        stmt = (
            select(Step.id, Step.name, func.count(Lawsuit.id))
            .select_from(Step)
            .outerjoin(Stage, Stage.step_id == Step.id)
            .outerjoin(Lawsuit, lawsuit_join)
            .group_by(Step.id, Step.name)
            .order_by(Step.position)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            PortfolioStepRow(step_id=int(step_id), step_name=name, active=int(count))
            for step_id, name, count in rows
        ]

    async def portfolio_by_period(
        self, *, first_month: date, action_group_id: uuid.UUID | None
    ) -> Sequence[PortfolioPeriodRow]:
        """Resumo da carteira por mês de criação (tempo real), últimos 12 meses."""
        month_expr = func.date_trunc("month", Lawsuit.created_at).cast(Date)
        stmt = (
            select(month_expr, func.count())
            .select_from(Lawsuit)
            .join(LawsuitType, LawsuitType.id == Lawsuit.lawsuit_type_id)
            .where(
                Lawsuit.is_archived.is_(False),
                Lawsuit.archived_date.is_(None),
                Lawsuit.created_at >= first_month,
                *self._group_filter(action_group_id),
            )
            .group_by(month_expr)
            .order_by(month_expr.desc())
        )
        rows = (await self.session.execute(stmt)).all()
        return [PortfolioPeriodRow(month=month, active=int(count)) for month, count in rows]


class BiVintageRepository:
    """Agregações do BI de Safra e Qualidade (spec 075).

    - **view barreira `bi_vintage`** (matview, até 8 h de defasagem): a tabela de safra
      por ano de `closure_date` (regras 3 e 4);
    - **tempo real sobre `lawsuits`**: taxa de sucesso por grupo no período e a série
      mensal (regra 6) — a view é anual e não responde granularidade mensal, mesmo
      raciocínio do §9.2 da 074.

    Nenhuma query filtra tenant no WHERE: lawsuits/action_groups/lawsuit_types têm RLS
    e a view barreira embute o filtro na definição (migration 075).
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---- view materializada (safra por ano de fechamento) --------------------------

    async def vintage_years(
        self,
        *,
        from_year: int | None,
        to_year: int | None,
        action_group_id: uuid.UUID | None,
    ) -> Sequence[VintageYearRow]:
        """Regras 3, 4 e 8: uma linha por ano de `closure_date` com os 8 campos; safra
        sem nenhum fechamento simplesmente não existe na view, então não aparece.

        Sem filtro de grupo, os grupos são somados por ano — `avg_cycle_days` vira
        média ponderada pelos arquivados (média de médias distorceria a regra 7)."""
        conditions: list[ColumnElement[bool]] = []
        if from_year is not None:
            conditions.append(bi_vintage.c.vintage_year >= from_year)
        if to_year is not None:
            conditions.append(bi_vintage.c.vintage_year <= to_year)
        if action_group_id is not None:
            conditions.append(bi_vintage.c.action_group_id == action_group_id)
        stmt = (
            select(
                bi_vintage.c.vintage_year,
                func.sum(bi_vintage.c.total),
                func.sum(bi_vintage.c.won),
                func.sum(bi_vintage.c.lost),
                func.sum(bi_vintage.c.settled),
                func.sum(bi_vintage.c.in_progress),
                func.sum(bi_vintage.c.transited),
                func.sum(bi_vintage.c.archived),
                (
                    func.sum(bi_vintage.c.avg_cycle_days * bi_vintage.c.archived)
                    / func.nullif(func.sum(bi_vintage.c.archived), 0)
                ),
            )
            .where(*conditions)
            .group_by(bi_vintage.c.vintage_year)
            .order_by(bi_vintage.c.vintage_year)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            VintageYearRow(
                vintage_year=int(year),
                total=int(total),
                won=int(won),
                lost=int(lost),
                settled=int(settled),
                in_progress=int(in_progress),
                transited=int(transited),
                archived=int(archived),
                avg_cycle_days=(round(float(avg_cycle), 1) if avg_cycle is not None else None),
            )
            for year, total, won, lost, settled, in_progress, transited, archived, avg_cycle in rows
        ]

    # ---- tempo real sobre lawsuits ------------------------------------------------

    async def success_by_group(
        self, *, month_start: date, month_end: date, action_group_id: uuid.UUID | None
    ) -> Sequence[SuccessGroupRow]:
        """Regra 1: só concluídos (`outcome` preenchido) com fechamento no período
        contam — em tramitação fica de fora. TODOS os grupos ativos aparecem (LEFT
        JOIN); quem não tem concluído no período vem zerado, nunca some."""
        concluded_join = and_(
            Lawsuit.lawsuit_type_id == LawsuitType.id,
            Lawsuit.outcome.is_not(None),
            Lawsuit.closure_date >= month_start,
            Lawsuit.closure_date <= month_end,
        )
        group_filter = [ActionGroup.id == action_group_id] if action_group_id else []
        stmt = (
            select(
                ActionGroup.id,
                ActionGroup.name,
                func.count(Lawsuit.id).filter(Lawsuit.outcome == LawsuitOutcome.GANHO),
                func.count(Lawsuit.id).filter(Lawsuit.outcome == LawsuitOutcome.PERDIDO),
                func.count(Lawsuit.id).filter(Lawsuit.outcome == LawsuitOutcome.ACORDO),
            )
            .select_from(ActionGroup)
            .outerjoin(LawsuitType, LawsuitType.action_group_id == ActionGroup.id)
            .outerjoin(Lawsuit, concluded_join)
            .where(ActionGroup.is_active.is_(True), *group_filter)
            .group_by(ActionGroup.id, ActionGroup.name)
            .order_by(ActionGroup.name)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            SuccessGroupRow(
                action_group_id=group_id,
                action_group_name=name,
                won=int(won),
                lost=int(lost),
                settled=int(settled),
            )
            for group_id, name, won, lost, settled in rows
        ]

    async def success_trend(
        self, *, first_month: date, action_group_id: uuid.UUID | None
    ) -> dict[date, SuccessMonthRow]:
        """Série mensal de ganhos/perdidos/acordos entre concluídos (regras 1 e 6) —
        o service completa os meses sem concluído com zeros e taxa None."""
        month_expr = func.date_trunc("month", Lawsuit.closure_date).cast(Date)
        group_filter = [LawsuitType.action_group_id == action_group_id] if action_group_id else []
        stmt = (
            select(
                month_expr,
                func.count().filter(Lawsuit.outcome == LawsuitOutcome.GANHO),
                func.count().filter(Lawsuit.outcome == LawsuitOutcome.PERDIDO),
                func.count().filter(Lawsuit.outcome == LawsuitOutcome.ACORDO),
            )
            .select_from(Lawsuit)
            .join(LawsuitType, LawsuitType.id == Lawsuit.lawsuit_type_id)
            .where(
                Lawsuit.outcome.is_not(None),
                Lawsuit.closure_date >= first_month,
                *group_filter,
            )
            .group_by(month_expr)
        )
        rows = (await self.session.execute(stmt)).all()
        return {
            month: SuccessMonthRow(month=month, won=int(won), lost=int(lost), settled=int(settled))
            for month, won, lost, settled in rows
        }


# ---- Spec 076 — BI: Tempo e Honorários ----------------------------------------------

_MONTH_DAYS = 30.0


def _monthly_fees_expr() -> ColumnElement[float | Decimal]:
    """Honorários ÷ meses de duração do processo (regras 4 e 8): `fees_value` ÷
    (rotação completa ÷ 30). O NULLIF faz rotação zero ou nula virar NULL — excluída
    da média pelo AVG, nunca divisão por zero nem valor inventado (regra 2)."""
    return (
        func.coalesce(bi_lawsuit_cycles.c.fees_value, 0)
        * _MONTH_DAYS
        / func.nullif(bi_lawsuit_cycles.c.full_cycle_days, 0)
    )


class BiTimeFeesRepository:
    """Agregações do BI de Tempo e Honorários (spec 076) — tudo da view barreira
    `bi_lawsuit_cycles` (matview, até 8 h de defasagem): o recorte é de processos
    FECHADOS e os 4 ciclos já vêm calculados por linha (regras 1 e 2).

    Nenhuma query filtra tenant no WHERE: a view barreira embute o filtro na definição
    (migration 076); action_groups/lawsuit_types, usados só para o nome, têm RLS.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _filters(
        self,
        *,
        from_: date | None,
        to: date | None,
        outcome: LawsuitOutcome | None,
        action_group_id: uuid.UUID | None,
    ) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = []
        if from_ is not None:
            conditions.append(bi_lawsuit_cycles.c.closure_date >= from_)
        if to is not None:
            conditions.append(bi_lawsuit_cycles.c.closure_date <= to)
        if outcome is not None:
            conditions.append(bi_lawsuit_cycles.c.outcome == outcome)
        if action_group_id is not None:
            conditions.append(bi_lawsuit_cycles.c.action_group_id == action_group_id)
        return conditions

    async def time_fees(
        self,
        *,
        from_: date | None,
        to: date | None,
        outcome: LawsuitOutcome | None,
        action_group_id: uuid.UUID | None,
    ) -> TimeFeesAggregateRow:
        """Regras 3 e 4: soma de honorários e contagem para a média por processo,
        média mensal (honorários ÷ meses) e as 4 médias de ciclo — AVG ignora nulos,
        que é exatamente a semântica da regra 2."""
        stmt = select(
            func.count(),
            func.coalesce(func.sum(bi_lawsuit_cycles.c.fees_value), 0),
            func.avg(bi_lawsuit_cycles.c.prospecting_days),
            func.avg(bi_lawsuit_cycles.c.production_days),
            func.avg(bi_lawsuit_cycles.c.execution_days),
            func.avg(bi_lawsuit_cycles.c.full_cycle_days),
            func.avg(_monthly_fees_expr()),
        ).where(
            *self._filters(from_=from_, to=to, outcome=outcome, action_group_id=action_group_id)
        )
        row = (await self.session.execute(stmt)).one()
        return TimeFeesAggregateRow(
            lawsuits=int(row[0]),
            total_fees=Decimal(row[1]),
            avg_prospecting_days=float(row[2]) if row[2] is not None else None,
            avg_production_days=float(row[3]) if row[3] is not None else None,
            avg_execution_days=float(row[4]) if row[4] is not None else None,
            avg_full_cycle_days=float(row[5]) if row[5] is not None else None,
            avg_monthly_fees=float(row[6]) if row[6] is not None else None,
        )

    async def cycles_by_group(self) -> Sequence[CycleGroupRow]:
        """Regra 10: os 4 ciclos médios lado a lado por grupo de ação — só grupos com
        processo fechado aparecem (a view só tem fechados)."""
        stmt = (
            select(
                ActionGroup.id,
                ActionGroup.name,
                func.count(bi_lawsuit_cycles.c.lawsuit_id),
                func.avg(bi_lawsuit_cycles.c.prospecting_days),
                func.avg(bi_lawsuit_cycles.c.production_days),
                func.avg(bi_lawsuit_cycles.c.execution_days),
                func.avg(bi_lawsuit_cycles.c.full_cycle_days),
            )
            .select_from(bi_lawsuit_cycles)
            .join(ActionGroup, ActionGroup.id == bi_lawsuit_cycles.c.action_group_id)
            .group_by(ActionGroup.id, ActionGroup.name)
            .order_by(ActionGroup.name)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            CycleGroupRow(
                action_group_id=group_id,
                action_group_name=name,
                lawsuits=int(lawsuits),
                avg_prospecting_days=float(prospecting) if prospecting is not None else None,
                avg_production_days=float(production) if production is not None else None,
                avg_execution_days=float(execution) if execution is not None else None,
                avg_full_cycle_days=float(full_cycle) if full_cycle is not None else None,
            )
            for group_id, name, lawsuits, prospecting, production, execution, full_cycle in rows
        ]

    async def profitability_by_type(
        self, *, lawsuit_type_id: uuid.UUID | None
    ) -> Sequence[ProfitabilityTypeRow]:
        """Regra 8: média de (`fees_value` ÷ meses) por tipo de ação."""
        conditions = (
            [bi_lawsuit_cycles.c.lawsuit_type_id == lawsuit_type_id]
            if lawsuit_type_id is not None
            else []
        )
        stmt = (
            select(
                LawsuitType.id,
                LawsuitType.name,
                func.count(bi_lawsuit_cycles.c.lawsuit_id),
                func.avg(_monthly_fees_expr()),
            )
            .select_from(bi_lawsuit_cycles)
            .join(LawsuitType, LawsuitType.id == bi_lawsuit_cycles.c.lawsuit_type_id)
            .where(*conditions)
            .group_by(LawsuitType.id, LawsuitType.name)
            .order_by(LawsuitType.name)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            ProfitabilityTypeRow(
                lawsuit_type_id=type_id,
                lawsuit_type_name=name,
                lawsuits=int(lawsuits),
                monthly_profitability=float(monthly) if monthly is not None else None,
            )
            for type_id, name, lawsuits, monthly in rows
        ]

    async def lost_time(self) -> LostTimeRow:
        """Regra 5: soma dos meses dos processos com `revenue = 0` e rotação completa
        maior que zero — processo sem receita mas com ciclo medível."""
        condition = and_(
            bi_lawsuit_cycles.c.revenue == 0,
            bi_lawsuit_cycles.c.full_cycle_days > 0,
        )
        stmt = select(
            func.count().filter(condition),
            func.coalesce(
                func.sum(bi_lawsuit_cycles.c.full_cycle_days / _MONTH_DAYS).filter(condition), 0
            ),
        ).select_from(bi_lawsuit_cycles)
        row = (await self.session.execute(stmt)).one()
        return LostTimeRow(
            zero_revenue_lawsuits=int(row[0]),
            lost_months=float(row[1]),
        )
