"""Regras de negócio do BI de Estoque e Prospecção (spec 074, regras 1–12), Safra e
Qualidade (075) e Tempo e Honorários (076)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dates import month_end, previous_month_start, shift_month
from app.core.materialized_view import MATERIALIZED_VIEWS, MaterializedViewSpec
from app.core.ratios import safe_percentage, safe_ratio
from app.domain.aggregates.schemas import AggregateMeta
from app.domain.aggregates.service import realtime_meta, view_meta
from app.domain.bi.models import SuccessMonthRow
from app.domain.bi.repository import (
    BiCostsRepository,
    BiPipelineRepository,
    BiTimeFeesRepository,
    BiVintageRepository,
)
from app.domain.bi.schemas import (
    CacResponse,
    ClosedMonthCard,
    ClosedTrendPoint,
    ConversionGroupItem,
    ConversionResponse,
    CostLawsuitItem,
    CostPerPointResponse,
    CostsByStageResponse,
    CostsResponse,
    CostStageItem,
    CycleAverages,
    LostTimeResponse,
    PipelineResponse,
    PortfolioPeriodItem,
    PortfolioResponse,
    PortfolioStepItem,
    SuccessRateGroupItem,
    SuccessRateResponse,
    SuccessTrendPoint,
    SuccessTrendResponse,
    TimeFeesByGroupResponse,
    TimeFeesByTypeResponse,
    TimeFeesGroupItem,
    TimeFeesResponse,
    TimeFeesTypeItem,
    VintageResponse,
    VintageYearItem,
)
from app.domain.lawsuits.models import LawsuitOutcome

_BI_VIEW = next(v for v in MATERIALIZED_VIEWS if v.view_name == "bi_pipeline_monthly")


async def _meta(session: AsyncSession, view: MaterializedViewSpec) -> AggregateMeta:
    """Atalho dos services de BI: envelope `meta` (spec 078, §5) da view associada."""
    return await view_meta(session, view.view_name, now=datetime.now(UTC))


_IDLE_DAYS = 120
_TREND_MONTHS = 6
_PORTFOLIO_PERIOD_MONTHS = 12

# Regra 12: aviso permanente na aba — o funil só é confiável se o CRM estiver alimentado.
CRM_WARNING = (
    "A qualidade destes indicadores depende do CRM alimentado: processos sem "
    "movimentação registrada ou sem datas de ciclo distorcem o funil."
)


def _delta(current: int, previous: int) -> float | None:
    """Anterior zerado → None ("novo" na UI), nunca ∞ — mesmo idioma da spec 028."""
    return safe_percentage(current - previous, previous)


def _month_start(value: date) -> date:
    return value.replace(day=1)


class BiPipelineService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.repo = BiPipelineRepository(session)
        self.tenant_id = tenant_id

    async def pipeline(
        self,
        *,
        from_: date | None,
        to: date | None,
        action_group_id: uuid.UUID | None,
        today: date,
    ) -> PipelineResponse:
        """Os 6 indicadores (regras 1–6). Janela padrão: mês corrente; a variação dos
        fechamentos compara com o mês imediatamente anterior ao início da janela."""
        end = to or today
        start = from_ or _month_start(end)
        previous_start = previous_month_start(start)
        previous_end = start - timedelta(days=1)

        opportunities = await self.repo.opportunities(
            month_start=_month_start(start),
            month_end=_month_start(end),
            action_group_id=action_group_id,
        )
        stock = await self.repo.stock_counts(
            idle_cutoff=datetime.now(UTC) - timedelta(days=_IDLE_DAYS),
            action_group_id=action_group_id,
        )
        closed, closed_prev = await self.repo.closed_counts(
            start=start,
            end=end,
            previous_start=previous_start,
            previous_end=previous_end,
            action_group_id=action_group_id,
        )
        trend = await self._closed_trend(end=end, action_group_id=action_group_id)

        return PipelineResponse(
            opportunities_month=opportunities,
            active=stock.active,
            archived=stock.archived,
            idle_120=stock.idle_120,
            closed_month=ClosedMonthCard(
                value=closed, delta_pct=_delta(closed, closed_prev), previous=closed_prev
            ),
            in_service=stock.in_service,
            closed_trend=trend,
            staleness_hint=_BI_VIEW.staleness_hint(),
            crm_warning=CRM_WARNING,
            meta=await _meta(self.repo.session, _BI_VIEW),
        )

    async def _closed_trend(
        self, *, end: date, action_group_id: uuid.UUID | None
    ) -> list[ClosedTrendPoint]:
        """Série de 6 meses terminando no mês de `end` — meses sem fechamento vêm
        zerados, nunca somem (mesmo espírito da regra 10)."""
        end_month = _month_start(end)
        first_year, first_month = shift_month(end_month.year, end_month.month, -(_TREND_MONTHS - 1))
        first = date(first_year, first_month, 1)
        by_month = await self.repo.closed_trend(first_month=first, action_group_id=action_group_id)
        points: list[ClosedTrendPoint] = []
        for offset in range(_TREND_MONTHS):
            year, month = shift_month(first.year, first.month, offset)
            month_date = date(year, month, 1)
            points.append(ClosedTrendPoint(month=month_date, closed=by_month.get(month_date, 0)))
        return points

    async def conversion(self, *, period: date) -> ConversionResponse:
        """Regra 7: taxa = fechados ÷ oportunidades da coorte, por grupo de ação."""
        rows = await self.repo.conversion_by_group(period=period)
        return ConversionResponse(
            period=period,
            groups=[
                ConversionGroupItem(
                    action_group_id=row.action_group_id,
                    action_group_name=row.action_group_name,
                    opportunities=row.opportunities,
                    closed=row.closed,
                    # Regra 11: zero oportunidades → None (a UI exibe "—"), nunca 0%.
                    conversion_rate=safe_percentage(row.closed, row.opportunities),
                )
                for row in rows
            ],
            staleness_hint=_BI_VIEW.staleness_hint(),
            meta=await _meta(self.repo.session, _BI_VIEW),
        )

    async def portfolio(
        self,
        *,
        group_by: str,
        action_group_id: uuid.UUID | None,
        today: date,
    ) -> PortfolioResponse:
        """Resumo da carteira do rodapé — tempo real (regra 8), sem cache nem view."""
        if group_by == "step":
            step_rows = await self.repo.portfolio_by_step(action_group_id=action_group_id)
            return PortfolioResponse(
                group_by="step",
                items=[
                    PortfolioStepItem(
                        step_id=row.step_id, step_name=row.step_name, active=row.active
                    )
                    for row in step_rows
                ],
                meta=realtime_meta(),
            )
        first_year, first_month = shift_month(
            today.year, today.month, -(_PORTFOLIO_PERIOD_MONTHS - 1)
        )
        period_rows = await self.repo.portfolio_by_period(
            first_month=date(first_year, first_month, 1), action_group_id=action_group_id
        )
        return PortfolioResponse(
            group_by="period",
            items=[PortfolioPeriodItem(month=row.month, active=row.active) for row in period_rows],
            meta=realtime_meta(),
        )


# ---- Spec 075 — BI: Safra e Qualidade ----------------------------------------------

_BI_VINTAGE_VIEW = next(v for v in MATERIALIZED_VIEWS if v.view_name == "bi_vintage")

# Regra 5: menos de 10 concluídos na safra/período → aviso de amostra pequena.
_SMALL_SAMPLE_THRESHOLD = 10
# Regra 9: variação acima de 10 pontos percentuais entre safras consecutivas é destacada.
_HIGHLIGHT_PP = 10.0
# Regra 6: a série da taxa (sparkline e gráfico) cobre os últimos 24 meses por padrão.
_DEFAULT_TREND_MONTHS = 24

# Regra 2: o critério da taxa é decisão de negócio e precisa estar explícito na UI
# (tooltip) — o texto mora aqui para os dois endpoints compartilharem a mesma redação.
RATE_NOTE = (
    "Taxa de sucesso = ganhos ÷ (ganhos + perdidos + acordos), calculada só sobre "
    "processos concluídos. Acordos entram no denominador, mas não no numerador."
)


def _success_rate(won: int, lost: int, settled: int) -> float | None:
    """Regras 1, 2 e 11: taxa = ganhos ÷ concluídos; zero concluídos → None ("—" na
    UI), nunca NaN ou 0%."""
    return safe_percentage(won, won + lost + settled)


def _small_sample(won: int, lost: int, settled: int) -> bool:
    """Regra 5: menos de 10 concluídos → amostra pequena."""
    return won + lost + settled < _SMALL_SAMPLE_THRESHOLD


class BiVintageService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.repo = BiVintageRepository(session)
        self.tenant_id = tenant_id

    async def vintage(
        self,
        *,
        from_year: int | None,
        to_year: int | None,
        action_group_id: uuid.UUID | None,
    ) -> VintageResponse:
        """Tabela de safra (regras 3, 4, 8) da view barreira + derivados: taxa
        (regras 1, 2, 11), aviso de amostra (regra 5) e comparação entre safras
        consecutivas (regra 9)."""
        rows = await self.repo.vintage_years(
            from_year=from_year, to_year=to_year, action_group_id=action_group_id
        )
        years: list[VintageYearItem] = []
        previous_rate: float | None = None
        for row in rows:
            rate = _success_rate(row.won, row.lost, row.settled)
            # Regra 9: só há comparação quando as duas safras têm taxa calculável.
            change = (
                round(rate - previous_rate, 1)
                if rate is not None and previous_rate is not None
                else None
            )
            years.append(
                VintageYearItem(
                    vintage_year=row.vintage_year,
                    total=row.total,
                    won=row.won,
                    lost=row.lost,
                    settled=row.settled,
                    in_progress=row.in_progress,
                    transited=row.transited,
                    archived=row.archived,
                    avg_cycle_days=row.avg_cycle_days,
                    success_rate=rate,
                    small_sample=_small_sample(row.won, row.lost, row.settled),
                    rate_change_pp=change,
                    highlighted=change is not None and abs(change) > _HIGHLIGHT_PP,
                )
            )
            previous_rate = rate
        return VintageResponse(
            years=years,
            staleness_hint=_BI_VINTAGE_VIEW.staleness_hint(),
            meta=await _meta(self.repo.session, _BI_VINTAGE_VIEW),
        )

    async def success_rate(
        self, *, period: date, action_group_id: uuid.UUID | None
    ) -> SuccessRateResponse:
        """Taxa de sucesso por grupo de ação no mês (regras 1, 2, 5 e 11) — tempo
        real: a view é anual e não responde um mês específico (§9.2 da 074)."""
        rows = await self.repo.success_by_group(
            month_start=period,
            month_end=month_end(period.year, period.month),
            action_group_id=action_group_id,
        )
        return SuccessRateResponse(
            period=period,
            groups=[
                SuccessRateGroupItem(
                    action_group_id=row.action_group_id,
                    action_group_name=row.action_group_name,
                    won=row.won,
                    lost=row.lost,
                    settled=row.settled,
                    concluded=row.won + row.lost + row.settled,
                    success_rate=_success_rate(row.won, row.lost, row.settled),
                    small_sample=_small_sample(row.won, row.lost, row.settled),
                )
                for row in rows
            ],
            rate_note=RATE_NOTE,
            meta=realtime_meta(),
        )

    async def success_trend(
        self, *, action_group_id: uuid.UUID | None, months: int, today: date
    ) -> SuccessTrendResponse:
        """Regra 6: série mensal terminando no mês corrente — meses sem concluído
        aparecem zerados com taxa None, nunca somem."""
        months = months or _DEFAULT_TREND_MONTHS
        end_month = today.replace(day=1)
        first_year, first_month = shift_month(end_month.year, end_month.month, -(months - 1))
        first = date(first_year, first_month, 1)
        by_month = await self.repo.success_trend(first_month=first, action_group_id=action_group_id)
        points: list[SuccessTrendPoint] = []
        for offset in range(months):
            year, month = shift_month(first.year, first.month, offset)
            month_date = date(year, month, 1)
            empty = SuccessMonthRow(month=month_date, won=0, lost=0, settled=0)
            row = by_month.get(month_date, empty)
            concluded = row.won + row.lost + row.settled
            points.append(
                SuccessTrendPoint(
                    month=month_date,
                    won=row.won,
                    lost=row.lost,
                    settled=row.settled,
                    concluded=concluded,
                    success_rate=_success_rate(row.won, row.lost, row.settled),
                )
            )
        return SuccessTrendResponse(
            months=months, points=points, rate_note=RATE_NOTE, meta=realtime_meta()
        )


# ---- Spec 076 — BI: Tempo e Honorários ----------------------------------------------

_BI_CYCLES_VIEW = next(v for v in MATERIALIZED_VIEWS if v.view_name == "bi_lawsuit_cycles")

# Regra 9: tipo de ação com menos de 5 processos no recorte → aviso de amostra pequena.
_SMALL_TYPE_SAMPLE_THRESHOLD = 5


@dataclass(frozen=True)
class CycleDays:
    """Os 4 ciclos de um processo, em dias (regra 1) — cada um None quando falta uma
    das datas do par (regra 2: nulo é "não sei", nunca zero; zero só existe quando as
    duas datas coincidem)."""

    prospecting_days: int | None
    production_days: int | None
    execution_days: int | None
    full_cycle_days: int | None


def compute_cycle_days(
    *,
    created: date,
    closure: date | None,
    transit: date | None,
    archived: date | None,
) -> CycleDays:
    """Definição canônica dos 4 ciclos (regras 1 e 2) — a matview `bi_lawsuit_cycles`
    (migration 076) espelha exatamente esta aritmética em SQL; esta função existe para
    os testes de unidade do plano (§8) exercitarem a regra sem banco."""
    return CycleDays(
        prospecting_days=(closure - created).days if closure is not None else None,
        production_days=(
            (transit - closure).days if transit is not None and closure is not None else None
        ),
        execution_days=(
            (archived - transit).days if archived is not None and transit is not None else None
        ),
        full_cycle_days=(archived - created).days if archived is not None else None,
    )


class BiTimeFeesService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.repo = BiTimeFeesRepository(session)
        self.tenant_id = tenant_id

    async def time_fees(
        self,
        *,
        from_: date | None,
        to: date | None,
        outcome: LawsuitOutcome | None,
        action_group_id: uuid.UUID | None,
    ) -> TimeFeesResponse:
        """Regras 3, 4 e 7: o recorte (resultado, janela de fechamento, grupo)
        recalcula tudo; recorte vazio → médias None ("—" na UI), nunca zero."""
        row = await self.repo.time_fees(
            from_=from_, to=to, outcome=outcome, action_group_id=action_group_id
        )
        return TimeFeesResponse(
            lawsuits=row.lawsuits,
            # Regra 3: soma ÷ processos no filtro; zero processos → None, não 0,00.
            avg_fees=safe_ratio(row.total_fees, row.lawsuits),
            avg_monthly_fees=(
                round(row.avg_monthly_fees, 2) if row.avg_monthly_fees is not None else None
            ),
            cycles=CycleAverages(
                prospecting_days=_round_days(row.avg_prospecting_days),
                production_days=_round_days(row.avg_production_days),
                execution_days=_round_days(row.avg_execution_days),
                full_cycle_days=_round_days(row.avg_full_cycle_days),
            ),
            staleness_hint=_BI_CYCLES_VIEW.staleness_hint(),
            meta=await _meta(self.repo.session, _BI_CYCLES_VIEW),
        )

    async def cycles_by_group(self) -> TimeFeesByGroupResponse:
        """Regra 10: os 4 ciclos lado a lado por grupo de ação."""
        rows = await self.repo.cycles_by_group()
        return TimeFeesByGroupResponse(
            groups=[
                TimeFeesGroupItem(
                    action_group_id=row.action_group_id,
                    action_group_name=row.action_group_name,
                    lawsuits=row.lawsuits,
                    cycles=CycleAverages(
                        prospecting_days=_round_days(row.avg_prospecting_days),
                        production_days=_round_days(row.avg_production_days),
                        execution_days=_round_days(row.avg_execution_days),
                        full_cycle_days=_round_days(row.avg_full_cycle_days),
                    ),
                )
                for row in rows
            ],
            staleness_hint=_BI_CYCLES_VIEW.staleness_hint(),
            meta=await _meta(self.repo.session, _BI_CYCLES_VIEW),
        )

    async def profitability_by_type(
        self, *, lawsuit_type_id: uuid.UUID | None
    ) -> TimeFeesByTypeResponse:
        """Regras 8 e 9: rentabilidade mensal por tipo + aviso de amostra pequena."""
        rows = await self.repo.profitability_by_type(lawsuit_type_id=lawsuit_type_id)
        return TimeFeesByTypeResponse(
            types=[
                TimeFeesTypeItem(
                    lawsuit_type_id=row.lawsuit_type_id,
                    lawsuit_type_name=row.lawsuit_type_name,
                    lawsuits=row.lawsuits,
                    monthly_profitability=(
                        round(row.monthly_profitability, 2)
                        if row.monthly_profitability is not None
                        else None
                    ),
                    small_sample=row.lawsuits < _SMALL_TYPE_SAMPLE_THRESHOLD,
                )
                for row in rows
            ],
            staleness_hint=_BI_CYCLES_VIEW.staleness_hint(),
            meta=await _meta(self.repo.session, _BI_CYCLES_VIEW),
        )

    async def lost_time(self) -> LostTimeResponse:
        """Regra 5: meses consumidos por processos sem receita paga."""
        row = await self.repo.lost_time()
        return LostTimeResponse(
            zero_revenue_lawsuits=row.zero_revenue_lawsuits,
            lost_months=round(row.lost_months, 1),
            staleness_hint=_BI_CYCLES_VIEW.staleness_hint(),
            meta=await _meta(self.repo.session, _BI_CYCLES_VIEW),
        )


def _round_days(value: float | None) -> float | None:
    """Médias de ciclo com 1 casa (mesmo idioma do avg_cycle_days da 075)."""
    return round(value, 1) if value is not None else None


# ---- Spec 077 — BI: Custos ----------------------------------------------------------

_BI_COSTS_VIEW = next(v for v in MATERIALIZED_VIEWS if v.view_name == "bi_cost_allocation")

# Regra 11: o rateio é aproximação e a fórmula vai na resposta para a UI explicá-la no
# tooltip (AllocationExplainer) — o texto mora aqui para os endpoints compartilharem a
# mesma redação (mesmo padrão do RATE_NOTE da 075).
ALLOCATION_NOTE = (
    "Custo alocado = custo direto (despesas lançadas no processo) + pontos das tarefas "
    "concluídas × custo por ponto do mês (custo fixo do mês ÷ pontos concluídos no mês). "
    "É uma aproximação de rateio, não contabilidade."
)

_STAGE_LABELS: dict[str, str] = {
    "prospecting": "Prospecção",
    "production": "Produção",
    "execution": "Execução",
    "full_cycle": "Rotação completa",
}


class BiCostsService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.repo = BiCostsRepository(session)
        self.tenant_id = tenant_id

    async def costs(
        self,
        *,
        outcome: LawsuitOutcome | None,
        from_year: int | None,
        to_year: int | None,
    ) -> CostsResponse:
        """Custo por processo (regras 4, 5, 6 e 7): direto + rateio dos pontos pelo
        custo por ponto do mês de cada conclusão. Processo em andamento entra — custo
        acontece antes do fechamento."""
        rows = await self.repo.lawsuit_costs(outcome=outcome, from_year=from_year, to_year=to_year)
        items: list[CostLawsuitItem] = []
        total_direct = 0.0
        total_allocated = 0.0
        for row in rows:
            direct = round(float(row.direct_cost), 2)
            points_cost = round(float(row.points_cost), 2) if row.points_cost is not None else None
            allocated = round(direct + (points_cost or 0.0), 2)
            total_direct += direct
            total_allocated += allocated
            items.append(
                CostLawsuitItem(
                    lawsuit_id=row.lawsuit_id,
                    folder=row.folder,
                    process_number=row.process_number,
                    # Regra 6: em andamento = sem arquivamento — custo corre antes do fim.
                    in_progress=row.archived_date is None,
                    direct_cost=direct,
                    points=row.points,
                    points_cost=points_cost,
                    allocated_cost=allocated,
                )
            )
        return CostsResponse(
            items=items,
            total_direct=round(total_direct, 2),
            total_allocated=round(total_allocated, 2),
            staleness_hint=_BI_COSTS_VIEW.staleness_hint(),
            allocation_note=ALLOCATION_NOTE,
            meta=await _meta(self.repo.session, _BI_COSTS_VIEW),
        )

    async def cac(self, *, period: date) -> CacResponse:
        """Regra 1: CAC = marketing (grupo DRE 8) ÷ clientes novos do mês. Regra 9:
        mês sem gasto de marketing → None, não zero; sem cliente novo → None, nunca
        infinito (regra 8)."""
        row = await self.repo.monthly_allocation(period=period)
        marketing = float(row.marketing_cost) if row is not None else 0.0
        new_customers = await self.repo.new_customers(month_start=period)
        # Marketing zerado não é CAC zero: é "não houve investimento no período".
        cac = safe_ratio(marketing, new_customers) if marketing > 0 else None
        return CacResponse(
            period=period,
            marketing_cost=round(marketing, 2),
            new_customers=new_customers,
            cac=cac,
            staleness_hint=_BI_COSTS_VIEW.staleness_hint(),
            meta=await _meta(self.repo.session, _BI_COSTS_VIEW),
        )

    async def per_point(self, *, period: date) -> CostPerPointResponse:
        """Regra 2: custo por ponto = custo fixo (grupos DRE 2, 3, 5 e 7) ÷ pontos
        concluídos no mês. Regra 8: mês sem pontos → None ("—"), nunca infinito — a
        própria view já entrega NULL pelo CASE."""
        row = await self.repo.monthly_allocation(period=period)
        fixed = float(row.fixed_cost) if row is not None else 0.0
        points = row.points if row is not None else None
        return CostPerPointResponse(
            period=period,
            fixed_cost=round(fixed, 2),
            points=points or 0,
            cost_per_point=(
                round(float(row.cost_per_point), 2)
                if row is not None and row.cost_per_point is not None
                else None
            ),
            staleness_hint=_BI_COSTS_VIEW.staleness_hint(),
            meta=await _meta(self.repo.session, _BI_COSTS_VIEW),
        )

    async def by_stage(self) -> CostsByStageResponse:
        """Custo médio por etapa do ciclo (escopo §2, regra 10) — em andamento incluso
        (regra 6): a etapa corrente conta os dias até hoje."""
        aggregates = await self.repo.cost_by_stage()
        return CostsByStageResponse(
            stages=[
                CostStageItem(
                    stage=stage,
                    label=_STAGE_LABELS[stage],
                    avg_days=_round_days(aggregate.avg_days),
                    avg_cost=(
                        round(aggregate.avg_cost, 2) if aggregate.avg_cost is not None else None
                    ),
                )
                for stage, aggregate in aggregates.items()
            ],
            staleness_hint=_BI_COSTS_VIEW.staleness_hint(),
            allocation_note=ALLOCATION_NOTE,
            meta=await _meta(self.repo.session, _BI_COSTS_VIEW),
        )
