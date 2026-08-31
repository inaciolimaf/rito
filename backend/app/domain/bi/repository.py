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
from typing import Any

from sqlalchemy import CTE, ColumnElement, Date, and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dates import next_month_start
from app.domain.action_groups.models import ActionGroup, LawsuitType
from app.domain.bi.models import (
    ConversionGroupRow,
    CostAllocationRow,
    CostLawsuitRow,
    CostStageAggregateRow,
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
    bi_cost_allocation,
    bi_lawsuit_cycles,
    bi_pipeline_monthly,
    bi_vintage,
)
from app.domain.customers.models import Customer
from app.domain.financial.models import Transaction, TransactionKind
from app.domain.lawsuits.models import Lawsuit, LawsuitOutcome
from app.domain.posts.models import Post, PostUser
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


# ---- Spec 077 — BI: Custos ----------------------------------------------------------


class BiCostsRepository:
    """Agregações do BI de Custos (spec 077).

    - **view barreira `bi_cost_allocation`** (matview, até 8 h de defasagem): custo
      fixo, marketing e custo por ponto por competência (regras 1 e 2);
    - **tempo real** sobre transactions/post_users/lawsuits/customers: custo direto
      por processo (regra 4), rateio (regra 5), clientes novos do CAC (regra 1) e o
      custo médio por etapa — custo acontece antes do fechamento, então processos em
      andamento entram (regra 6).

    Nenhuma query filtra tenant no WHERE: transactions/post_users/lawsuits/customers
    têm RLS e a view barreira embute o filtro na definição (migration 077) — por isso
    o join do rateio casa só pela competência.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---- view materializada (custo fixo/marketing/pontos por competência) ----------

    async def monthly_allocation(self, *, period: date) -> CostAllocationRow | None:
        """Uma competência da view — None quando o mês não teve nenhuma despesa."""
        stmt = select(
            bi_cost_allocation.c.fixed_cost,
            bi_cost_allocation.c.marketing_cost,
            bi_cost_allocation.c.points,
            bi_cost_allocation.c.cost_per_point,
        ).where(bi_cost_allocation.c.competence == period)
        row = (await self.session.execute(stmt)).one_or_none()
        if row is None:
            return None
        # SUM(...) FILTER rende NULL quando o mês não teve despesa daquele grupo (só
        # marketing sem fixo, ou vice-versa) — na leitura, NULL vira zero.
        return CostAllocationRow(
            fixed_cost=Decimal(row.fixed_cost) if row.fixed_cost is not None else Decimal(0),
            marketing_cost=(
                Decimal(row.marketing_cost) if row.marketing_cost is not None else Decimal(0)
            ),
            points=int(row.points) if row.points is not None else None,
            cost_per_point=Decimal(row.cost_per_point) if row.cost_per_point is not None else None,
        )

    # ---- tempo real ---------------------------------------------------------------

    async def new_customers(self, *, month_start: date) -> int:
        """Regra 1 (denominador do CAC): clientes criados no mês.

        O limite superior é o dia 1 do mês SEGUINTE, calculado aqui dentro. Antes o
        chamador passava `month_end` (que é o ÚLTIMO DIA do mês, não o primeiro do
        seguinte) e a comparação era `<`: como `created_at` é timestamp, `< 2026-08-31`
        significa "antes da meia-noite do dia 31" e o último dia inteiro do mês ficava
        de fora do denominador do CAC — todo mês, o ano todo.

        O bug só aparecia quando a suíte rodava NO último dia do mês (o cliente criado
        pelo teste caía justamente no dia descartado), e foi assim que ele apareceu:
        `make test` em 31/08/2026. Corrigido fora do escopo da spec 101 porque era ele
        que segurava o gate — mesmo precedente da 075 §9.10.

        Não é um `<=`: com timestamp, `<= 2026-08-31` continuaria cortando as 23h59 do
        dia. Quem compara data-a-data (`Lawsuit.closure_date`, `bi_pipeline_monthly.month`)
        segue usando `month_end` inclusivo, o que está certo para aqueles casos.
        """
        stmt = select(func.count()).where(
            Customer.created_at >= month_start,
            Customer.created_at < next_month_start(month_start),
        )
        return int(await self.session.scalar(stmt) or 0)

    def _direct_costs_cte(self) -> CTE:
        """Regra 4: despesa não interna com `lawsuit_id` — transferência tem kind
        próprio (spec 056) e interno é controle (spec 058): os dois ficam fora."""
        return (
            select(
                Transaction.lawsuit_id.label("lawsuit_id"),
                func.sum(Transaction.amount).label("direct_cost"),
            )
            .where(
                Transaction.kind == TransactionKind.DESPESA,
                Transaction.is_internal.is_(False),
                Transaction.lawsuit_id.is_not(None),
            )
            .group_by(Transaction.lawsuit_id)
            .cte("cost_direct")
        )

    def _allocated_costs_cte(self) -> CTE:
        """Regra 5: pontos concluídos do processo por mês × custo por ponto DAQUELE
        mês (da view). Mês sem custo por ponto calculável (regra 8) contribui NULL no
        somatório do rateio — o SUM ignora e os outros meses continuam valendo."""
        # Mesma expressão (mesmo objeto) no SELECT e no GROUP BY — duas instâncias
        # geram dois bind params ($4/$5) e o PG não reconhece a igualdade ("must
        # appear in the GROUP BY clause"); mesmo padrão do month_expr da 074/076.
        month_expr = func.date_trunc("month", PostUser.completed_at).cast(Date)
        monthly_points = (
            select(
                Post.lawsuit_id.label("lawsuit_id"),
                month_expr.label("competence"),
                func.sum(PostUser.points_earned).label("points"),
            )
            .select_from(PostUser)
            .join(Post, Post.id == PostUser.post_id)
            .where(PostUser.completed_at.is_not(None))
            .group_by(Post.lawsuit_id, month_expr)
            .cte("cost_points_monthly")
        )
        return (
            select(
                monthly_points.c.lawsuit_id,
                func.sum(monthly_points.c.points).label("points"),
                func.sum(monthly_points.c.points * bi_cost_allocation.c.cost_per_point).label(
                    "points_cost"
                ),
            )
            .select_from(monthly_points)
            .outerjoin(
                bi_cost_allocation,
                bi_cost_allocation.c.competence == monthly_points.c.competence,
            )
            .group_by(monthly_points.c.lawsuit_id)
            .cte("cost_allocated")
        )

    async def lawsuit_costs(
        self,
        *,
        outcome: LawsuitOutcome | None,
        from_year: int | None,
        to_year: int | None,
    ) -> Sequence[CostLawsuitRow]:
        """Regras 4, 5, 6 e 7: custo por processo — em andamento incluso (sem filtro
        de fechamento); o intervalo de anos usa `archived_date` e, sem arquivamento,
        cai para o ano de `created_at`."""
        direct = self._direct_costs_cte()
        allocated = self._allocated_costs_cte()
        year_expr = func.coalesce(
            func.extract("year", Lawsuit.archived_date),
            func.extract("year", Lawsuit.created_at),
        )
        conditions: list[ColumnElement[bool]] = []
        if outcome is not None:
            conditions.append(Lawsuit.outcome == outcome)
        if from_year is not None:
            conditions.append(year_expr >= from_year)
        if to_year is not None:
            conditions.append(year_expr <= to_year)
        stmt = (
            select(
                Lawsuit.id,
                Lawsuit.folder,
                Lawsuit.process_number,
                Lawsuit.created_at,
                Lawsuit.closure_date,
                Lawsuit.archived_date,
                Lawsuit.outcome,
                func.coalesce(direct.c.direct_cost, 0),
                func.coalesce(allocated.c.points, 0),
                allocated.c.points_cost,
            )
            .select_from(Lawsuit)
            .outerjoin(direct, direct.c.lawsuit_id == Lawsuit.id)
            .outerjoin(allocated, allocated.c.lawsuit_id == Lawsuit.id)
            .where(*conditions)
            .order_by(Lawsuit.created_at.desc())
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            CostLawsuitRow(
                lawsuit_id=lawsuit_id,
                folder=folder,
                process_number=process_number,
                created_at=created_at,
                closure_date=closure_date,
                archived_date=archived_date,
                outcome=outcome_value,
                direct_cost=Decimal(direct_cost),
                points=int(points),
                points_cost=Decimal(points_cost) if points_cost is not None else None,
            )
            for (
                lawsuit_id,
                folder,
                process_number,
                created_at,
                closure_date,
                archived_date,
                outcome_value,
                direct_cost,
                points,
                points_cost,
            ) in rows
        ]

    async def cost_by_stage(self) -> dict[str, CostStageAggregateRow]:
        """Custo médio por etapa do ciclo (escopo §2, regras 6 e 10): cada processo
        distribui o custo total (direto + rateio) pelas etapas na proporção dos dias
        — rateio por tempo, aproximação assumida (regra 11). Etapa ainda não alcançada
        é NULL e some da média pelo próprio AVG; rotação zero (criado hoje) também
        vira NULL via NULLIF — nunca divisão por zero (regra 8)."""
        direct = self._direct_costs_cte()
        allocated = self._allocated_costs_cte()
        today = func.current_date()
        created_day = Lawsuit.created_at.cast(Date)
        prospecting_days = func.coalesce(Lawsuit.closure_date, today) - created_day
        production_days = case(
            (
                Lawsuit.closure_date.is_not(None),
                func.coalesce(Lawsuit.transit_date, today) - Lawsuit.closure_date,
            ),
            else_=None,
        )
        execution_days = case(
            (
                Lawsuit.transit_date.is_not(None),
                func.coalesce(Lawsuit.archived_date, today) - Lawsuit.transit_date,
            ),
            else_=None,
        )
        full_cycle_days = func.coalesce(Lawsuit.archived_date, today) - created_day
        total_cost = func.coalesce(direct.c.direct_cost, 0) + func.coalesce(
            allocated.c.points_cost, 0
        )

        def stage_cost(phase_days: ColumnElement[int | None]) -> ColumnElement[Any]:
            return func.avg(total_cost * phase_days / func.nullif(full_cycle_days, 0))

        stmt = (
            select(
                func.avg(prospecting_days),
                stage_cost(prospecting_days),
                func.avg(production_days),
                stage_cost(production_days),
                func.avg(execution_days),
                stage_cost(execution_days),
                func.avg(full_cycle_days),
                stage_cost(full_cycle_days),
            )
            .select_from(Lawsuit)
            .outerjoin(direct, direct.c.lawsuit_id == Lawsuit.id)
            .outerjoin(allocated, allocated.c.lawsuit_id == Lawsuit.id)
        )
        row = (await self.session.execute(stmt)).one()

        def build(days: Any, cost: Any) -> CostStageAggregateRow:
            return CostStageAggregateRow(
                avg_days=float(days) if days is not None else None,
                avg_cost=float(cost) if cost is not None else None,
            )

        return {
            "prospecting": build(row[0], row[1]),
            "production": build(row[2], row[3]),
            "execution": build(row[4], row[5]),
            "full_cycle": build(row[6], row[7]),
        }
