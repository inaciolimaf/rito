"""BI — leituras das views barreira e tipos internos (specs 074, 075, 076 e 077).

A view materializada `bi_pipeline_monthly` (migration 074) agrega por (tenant, mês de
CRIAÇÃO, grupo de ação) — uma coorte: responde "das oportunidades que entraram no mês,
quantas fecharam", base da taxa de conversão (regra 7). Estoque (ativos, parados,
em atendimento) e fechamentos por `closure_date` são tempo real no repository
(regra 8: gráficos vêm da view, indicadores de estoque e relatórios são tempo real).

A view materializada `bi_vintage` (migration 075) agrega por (tenant, ANO de
`closure_date`, grupo de ação) — a safra (regra 3 da 075). A taxa de sucesso mensal
(período e série de 24 meses, regra 6) não é derivável de uma view anual e fica em
tempo real no repository — mesmo raciocínio do §9.2 da 074.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Column, Date, Integer, MetaData, Numeric, Table
from sqlalchemy.dialects.postgresql import ENUM as PGENUM
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.domain.lawsuits.models import LawsuitOutcome

# View barreira sobre a matview bi_pipeline_monthly (migration 074) — o filtro de tenant
# está na definição da view, então a aplicação consulta sem WHERE de tenant (CLAUDE.md §4).
# Tabela Core somente-leitura: nunca entra em create_all/migration, só em SELECTs.
bi_pipeline_monthly = Table(
    "bi_pipeline_monthly_visible",
    MetaData(),
    Column("tenant_id", PGUUID(as_uuid=True)),
    Column("month", Date),
    Column("action_group_id", PGUUID(as_uuid=True)),
    Column("opportunities", Integer),
    Column("closed", Integer),
    Column("archived", Integer),
    Column("total_case_value", Numeric),
    Column("closed_fees", Numeric),
)


@dataclass
class ConversionGroupRow:
    """Uma linha do funil por grupo de ação (regra 10: grupo sem movimento aparece
    zerado — o LEFT JOIN no repository garante a presença; a taxa None vira "—" na UI,
    regra 11)."""

    action_group_id: uuid.UUID
    action_group_name: str
    opportunities: int
    closed: int


@dataclass
class StockCounts:
    """Os indicadores de estoque (tempo real) — ver regras 2, 3, 4 e 6."""

    active: int
    archived: int
    idle_120: int
    in_service: int


@dataclass
class PortfolioStepRow:
    step_id: int
    step_name: str
    active: int


@dataclass
class PortfolioPeriodRow:
    month: date
    active: int


# View barreira sobre a matview bi_vintage (migration 075) — a safra agrega por (tenant,
# ANO de closure_date, grupo de ação); o filtro de tenant está na definição da view,
# então a aplicação consulta sem WHERE de tenant (CLAUDE.md §4).
bi_vintage = Table(
    "bi_vintage_visible",
    MetaData(),
    Column("tenant_id", PGUUID(as_uuid=True)),
    Column("vintage_year", Integer),
    Column("action_group_id", PGUUID(as_uuid=True)),
    Column("total", Integer),
    Column("won", Integer),
    Column("lost", Integer),
    Column("settled", Integer),
    Column("in_progress", Integer),
    Column("transited", Integer),
    Column("archived", Integer),
    Column("avg_cycle_days", Numeric),
)


@dataclass
class VintageYearRow:
    """Uma safra (regra 4): os 8 campos por ano de fechamento — `avg_cycle_days` é
    None quando a safra não tem nenhum arquivado (regra 7: a média só existe entre
    arquivados)."""

    vintage_year: int
    total: int
    won: int
    lost: int
    settled: int
    in_progress: int
    transited: int
    archived: int
    avg_cycle_days: float | None


@dataclass
class SuccessGroupRow:
    """Taxa de sucesso de um grupo num período (tempo real) — grupo sem concluídos no
    período aparece zerado (LEFT JOIN), nunca some; a taxa None vira "—" na UI
    (regra 11)."""

    action_group_id: uuid.UUID
    action_group_name: str
    won: int
    lost: int
    settled: int


@dataclass
class SuccessMonthRow:
    """Um mês da série de taxa de sucesso (tempo real) — meses sem concluído vêm
    zerados e o service completa a janela."""

    month: date
    won: int
    lost: int
    settled: int


# View barreira sobre a matview bi_lawsuit_cycles (migration 076) — uma linha por
# processo FECHADO com os 4 ciclos em dias, honorários e a receita paga vinculada;
# o filtro de tenant está na definição da view, então a aplicação consulta sem WHERE
# de tenant (CLAUDE.md §4).
bi_lawsuit_cycles = Table(
    "bi_lawsuit_cycles_visible",
    MetaData(),
    Column("tenant_id", PGUUID(as_uuid=True)),
    Column("lawsuit_id", PGUUID(as_uuid=True)),
    Column("action_group_id", PGUUID(as_uuid=True)),
    Column("lawsuit_type_id", PGUUID(as_uuid=True)),
    # O tipo enum real é necessário para o filtro `outcome = ...` — um bind VARCHAR
    # não tem operador contra lawsuit_outcome no Postgres.
    Column("outcome", PGENUM(LawsuitOutcome, name="lawsuit_outcome", create_type=False)),
    Column("created_date", Date),
    Column("closure_date", Date),
    Column("transit_date", Date),
    Column("archived_date", Date),
    Column("fees_value", Numeric),
    Column("prospecting_days", Integer),
    Column("production_days", Integer),
    Column("execution_days", Integer),
    Column("full_cycle_days", Integer),
    Column("revenue", Numeric),
)


@dataclass
class TimeFeesAggregateRow:
    """Os agregados do painel (regras 3 e 4) — `lawsuits` é o denominador da média de
    honorários; as médias dos 4 ciclos ignoram nulos (regra 2: AVG do Postgres já
    descarta NULL, exatamente a semântica pedida)."""

    lawsuits: int
    total_fees: Decimal
    avg_prospecting_days: float | None
    avg_production_days: float | None
    avg_execution_days: float | None
    avg_full_cycle_days: float | None
    avg_monthly_fees: float | None


@dataclass
class CycleGroupRow:
    """Uma linha do gráfico por grupo de ação (regra 10): as 4 médias de ciclo lado
    a lado — cada uma None quando nenhum processo do grupo tem o par de datas."""

    action_group_id: uuid.UUID
    action_group_name: str
    lawsuits: int
    avg_prospecting_days: float | None
    avg_production_days: float | None
    avg_execution_days: float | None
    avg_full_cycle_days: float | None


@dataclass
class ProfitabilityTypeRow:
    """Uma linha da rentabilidade por tipo de ação (regra 8): média de
    (`fees_value` ÷ meses de duração) dos processos do tipo."""

    lawsuit_type_id: uuid.UUID
    lawsuit_type_name: str
    lawsuits: int
    monthly_profitability: float | None


@dataclass
class LostTimeRow:
    """Tempo perdido (regra 5): processos sem nenhuma receita paga e com rotação
    completa maior que zero, e a soma dos meses que eles consumiram."""

    zero_revenue_lawsuits: int
    lost_months: float


# ---- Spec 077 — BI: Custos ----------------------------------------------------------


# View barreira sobre a matview bi_cost_allocation (migration 077) — uma linha por
# (tenant, competência) com custo fixo (grupos DRE 2/3/5/7), marketing (grupo 8),
# pontos do Taskscore e o custo por ponto derivado (regra 2); o filtro de tenant está
# na definição da view, então a aplicação consulta sem WHERE de tenant (CLAUDE.md §4).
bi_cost_allocation = Table(
    "bi_cost_allocation_visible",
    MetaData(),
    Column("tenant_id", PGUUID(as_uuid=True)),
    Column("competence", Date),
    Column("fixed_cost", Numeric),
    Column("marketing_cost", Numeric),
    Column("points", Numeric),
    Column("cost_per_point", Numeric),
)


@dataclass
class CostAllocationRow:
    """Uma competência da view (regras 1 e 2) — `points` e `cost_per_point` são None
    quando o mês não teve ponto concluído (regra 8: nulo é "—", nunca infinito)."""

    fixed_cost: Decimal
    marketing_cost: Decimal
    points: int | None
    cost_per_point: Decimal | None


@dataclass
class CostLawsuitRow:
    """Custo de um processo (regras 4, 5 e 6 — em andamento incluso): `direct_cost`
    são as despesas lançadas com `lawsuit_id`; `points_cost` é o rateio (pontos das
    tarefas × custo por ponto do mês de cada conclusão) — None quando nenhum mês das
    conclusões tem custo por ponto calculável; `points` é o total de pontos concluídos
    no processo, independente do rateio ser calculável."""

    lawsuit_id: uuid.UUID
    folder: str | None
    process_number: str | None
    created_at: datetime
    closure_date: date | None
    archived_date: date | None
    outcome: LawsuitOutcome | None
    direct_cost: Decimal
    points: int
    points_cost: Decimal | None


@dataclass
class CostStageAggregateRow:
    """Médias de uma etapa do ciclo (escopo §2: custo médio em produção, execução e
    rotação completa; regra 10: as 4 etapas do gráfico). `avg_cost` é a média do custo
    proporcional aos dias da etapa (rateio por tempo — aproximação, regra 11); None
    quando nenhum processo entrou na etapa com rotação maior que zero."""

    avg_days: float | None
    avg_cost: float | None
