import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.domain.aggregates.schemas import AggregateMeta


class ClosedMonthCard(BaseModel):
    """Fechamentos do período com variação (regra 5) — `delta_pct` None = período
    anterior zerado ("novo"), nunca ∞ (mesmo idioma do dashboard de processos, 028)."""

    value: int
    delta_pct: float | None
    previous: int


class ClosedTrendPoint(BaseModel):
    month: date
    closed: int


class PipelineResponse(BaseModel):
    """Os 6 indicadores da aba (regras 1–6) + série de 6 meses e os dois avisos
    obrigatórios: defasagem da view (regra 8) e dependência do CRM alimentado
    (regra 12). Spec 078, §5: `meta` carrega a defasagem estruturada da view."""

    opportunities_month: int
    active: int
    archived: int
    idle_120: int
    closed_month: ClosedMonthCard
    in_service: int
    closed_trend: list[ClosedTrendPoint]
    staleness_hint: str
    crm_warning: str
    meta: AggregateMeta


class ConversionGroupItem(BaseModel):
    action_group_id: uuid.UUID
    action_group_name: str
    opportunities: int
    closed: int
    # Regra 11: divisão por zero → None (a UI exibe "—"), nunca NaN ou 0%.
    conversion_rate: float | None


class ConversionResponse(BaseModel):
    period: date
    groups: list[ConversionGroupItem]
    staleness_hint: str
    meta: AggregateMeta


class PortfolioStepItem(BaseModel):
    step_id: int
    step_name: str
    active: int


class PortfolioPeriodItem(BaseModel):
    month: date
    active: int


PortfolioGroupBy = Literal["step", "period"]


class PortfolioResponse(BaseModel):
    """Resumo da carteira (tempo real, regra 8) agrupado por fase ou por período de
    criação — as duas formas compartilham a rota, discriminadas por `group_by`.
    Spec 078, §5: `meta` de tempo real (defasagem zero — não vem de view)."""

    group_by: PortfolioGroupBy
    items: list[PortfolioStepItem] | list[PortfolioPeriodItem]
    meta: AggregateMeta


# ---- Spec 075 — BI: Safra e Qualidade ----------------------------------------------


class VintageYearItem(BaseModel):
    """Uma linha da tabela de safra (regra 4): os 8 campos por ano de fechamento +
    os derivados — taxa de sucesso (regras 1, 2 e 11: None vira "—"), aviso de amostra
    (regra 5) e destaque de variação vs safra anterior (regra 9)."""

    vintage_year: int
    total: int
    won: int
    lost: int
    settled: int
    in_progress: int
    transited: int
    archived: int
    avg_cycle_days: float | None
    success_rate: float | None
    small_sample: bool
    rate_change_pp: float | None
    highlighted: bool


class VintageResponse(BaseModel):
    years: list[VintageYearItem]
    staleness_hint: str
    meta: AggregateMeta


class SuccessRateGroupItem(BaseModel):
    """Taxa de sucesso de um grupo de ação no período (regras 1 e 2). `concluded` =
    ganhos + perdidos + acordos; zero concluídos → `success_rate` None (regra 11);
    menos de 10 → `small_sample` (regra 5)."""

    action_group_id: uuid.UUID
    action_group_name: str
    won: int
    lost: int
    settled: int
    concluded: int
    success_rate: float | None
    small_sample: bool


class SuccessRateResponse(BaseModel):
    period: date
    groups: list[SuccessRateGroupItem]
    # Regra 2: o critério da taxa vai na resposta para a UI explicá-lo no tooltip.
    rate_note: str
    # Spec 078, §5: meta de tempo real (defasagem zero — calculado na hora, sem view).
    meta: AggregateMeta


class SuccessTrendPoint(BaseModel):
    """Um mês da série (regra 6: 24 meses) — mês sem concluído vem zerado com taxa
    None ("—" na UI), nunca some da série."""

    month: date
    won: int
    lost: int
    settled: int
    concluded: int
    success_rate: float | None


class SuccessTrendResponse(BaseModel):
    months: int
    points: list[SuccessTrendPoint]
    rate_note: str
    # Spec 078, §5: meta de tempo real (defasagem zero — calculado na hora, sem view).
    meta: AggregateMeta


# ---- Spec 076 — BI: Tempo e Honorários ----------------------------------------------


class CycleAverages(BaseModel):
    """As médias dos 4 ciclos em dias (regra 1) — cada uma None quando nenhum processo
    do recorte tem o par de datas (regra 2: nulo é "não sei", nunca zero)."""

    prospecting_days: float | None
    production_days: float | None
    execution_days: float | None
    full_cycle_days: float | None


class TimeFeesResponse(BaseModel):
    """Os indicadores do painel (regras 3 e 4). `avg_fees` = soma de `fees_value` ÷
    processos no filtro (None quando o recorte está vazio — "—" na UI, mesmo idioma da
    regra 11 da 074/075); `avg_monthly_fees` = média de (honorários ÷ meses de duração),
    None quando nenhum processo do recorte tem rotação completa maior que zero."""

    lawsuits: int
    avg_fees: float | None
    avg_monthly_fees: float | None
    cycles: CycleAverages
    staleness_hint: str
    meta: AggregateMeta


class TimeFeesGroupItem(BaseModel):
    """Um grupo de ação no gráfico dos 4 ciclos lado a lado (regra 10)."""

    action_group_id: uuid.UUID
    action_group_name: str
    lawsuits: int
    cycles: CycleAverages


class TimeFeesByGroupResponse(BaseModel):
    groups: list[TimeFeesGroupItem]
    staleness_hint: str
    meta: AggregateMeta


class TimeFeesTypeItem(BaseModel):
    """Rentabilidade mensal de um tipo de ação (regra 8) — `small_sample` marca tipo
    com menos de 5 processos (regra 9); `monthly_profitability` None quando nenhum
    processo do tipo tem rotação completa maior que zero ("—" na UI)."""

    lawsuit_type_id: uuid.UUID
    lawsuit_type_name: str
    lawsuits: int
    monthly_profitability: float | None
    small_sample: bool


class TimeFeesByTypeResponse(BaseModel):
    types: list[TimeFeesTypeItem]
    staleness_hint: str
    meta: AggregateMeta


class LostTimeResponse(BaseModel):
    """Tempo perdido (regra 5): meses consumidos por processos sem nenhuma receita
    paga e com rotação completa maior que zero."""

    zero_revenue_lawsuits: int
    lost_months: float
    staleness_hint: str
    meta: AggregateMeta


# ---- Spec 077 — BI: Custos ----------------------------------------------------------


class CostLawsuitItem(BaseModel):
    """Uma linha da tabela de custo por processo (regras 4, 5 e 6): custo direto
    (despesas com `lawsuit_id`), pontos concluídos, rateio (pontos × custo por ponto
    do mês) e o custo alocado (direto + rateio). `points_cost` None = nenhum mês das
    conclusões teve custo por ponto calculável ("—" na UI, regra 8); `in_progress`
    marca processo sem arquivamento (regra 6: em andamento entra no cálculo)."""

    lawsuit_id: uuid.UUID
    folder: str | None
    process_number: str | None
    in_progress: bool
    direct_cost: float
    points: int
    points_cost: float | None
    allocated_cost: float


class CostsResponse(BaseModel):
    """Custo por processo no recorte (resultado + intervalo de anos, regra 7) —
    tempo real sobre transactions/post_users; só o custo por ponto vem da view
    (até 8 h de defasagem, sinalizada no hint)."""

    items: list[CostLawsuitItem]
    total_direct: float
    total_allocated: float
    staleness_hint: str
    meta: AggregateMeta
    allocation_note: str


class CacResponse(BaseModel):
    """CAC do mês (regra 1): marketing (grupo DRE 8) ÷ clientes novos. `cac` None
    quando não houve gasto de marketing (regra 9: nulo, não zero) ou quando não houve
    cliente novo (divisão por zero, regra 8: nunca infinito)."""

    period: date
    marketing_cost: float
    new_customers: int
    cac: float | None
    staleness_hint: str
    meta: AggregateMeta


class CostPerPointResponse(BaseModel):
    """Custo por ponto do mês (regra 2): custo fixo (grupos DRE 2, 3, 5 e 7) ÷
    pontos do Taskscore concluídos. `cost_per_point` None quando o mês não teve
    ponto (regra 8: "—", nunca infinito)."""

    period: date
    fixed_cost: float
    points: int
    cost_per_point: float | None
    staleness_hint: str
    meta: AggregateMeta


class CostStageItem(BaseModel):
    """Uma etapa do gráfico custo/tempo (escopo §2 e regra 10): média de dias e média
    do custo proporcional aos dias da etapa. Ambas None quando nenhum processo entrou
    na etapa ("—" na UI)."""

    stage: str
    label: str
    avg_days: float | None
    avg_cost: float | None


class CostsByStageResponse(BaseModel):
    stages: list[CostStageItem]
    staleness_hint: str
    meta: AggregateMeta
    allocation_note: str
