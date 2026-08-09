import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

# Período do ranking/me: "YYYY-MM" ou "eltv" (vida toda — ADVBOX "VIDA TODA", spec 039 §5).
Period = str


class ClosureGoalItem(BaseModel):
    action_group_id: uuid.UUID
    monthly_target: int = Field(ge=0)


class ClosureGoalsPutRequest(BaseModel):
    """Upsert em lote (regra: grupos fora do payload ficam intactos)."""

    items: list[ClosureGoalItem]


class ClosureGoalResponse(BaseModel):
    action_group_id: uuid.UUID
    action_group_name: str
    monthly_target: int


class ClosureGoalsListResponse(BaseModel):
    items: list[ClosureGoalResponse]


class ScoreSummary(BaseModel):
    """Resumo de desempenho de um usuário num período — base do /me e das linhas do ranking."""

    user_id: uuid.UUID
    user_name: str
    points: int
    tasks_completed: int
    on_time: int
    late: int
    assigned: int
    engagement: float | None  # concluídas ÷ atribuídas; None = nada atribuído (regra 4)
    points_goal: int | None
    goal_pct: float | None  # None = sem meta → "—" (regra 3)


class MyScoreResponse(BaseModel):
    period: Period
    summary: ScoreSummary


class RankingResponse(BaseModel):
    period: Period
    sort: str
    items: list[ScoreSummary]


class ChartPoint(BaseModel):
    label: str
    value: int


class ScoreChartResponse(BaseModel):
    granularity: Literal["monthly", "daily"]
    # monthly: mês atual × mês anterior × meta (ADVBOX 4.1). A meta entra como terceira
    # barra pelo front; aqui vai o valor cru (None = sem meta).
    current: int
    previous: int
    goal: int | None
    # daily: pontos por dia do mês corrente (vazio na visão mensal).
    days: list[ChartPoint]


def parse_month(value: str) -> date:
    """ "YYYY-MM" → primeiro dia do mês; levanta ValueError fora desse formato."""
    parsed = date.fromisoformat(f"{value}-01")
    if len(value) != 7 or value[4] != "-":
        raise ValueError("Período deve ser YYYY-MM ou 'eltv'.")
    return parsed
