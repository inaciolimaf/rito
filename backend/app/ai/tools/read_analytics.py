"""Ferramentas de produtividade, BI, taxonomias e contexto (spec 083).

`get_bi_metrics` exige ADMINISTRADOR pelo mesmo motivo que a rota de BI exige (spec
074): indicador de escritório não é dado de colaborador. O agente herda o RBAC de quem
perguntou — não o contorna.
"""

import uuid
from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from app.ai.tools.base import ToolContext, ToolError, tool
from app.core.permissions import UserRole
from app.domain.action_groups.repository import ActionGroupRepository, LawsuitTypeRepository
from app.domain.bi.service import BiPipelineService
from app.domain.customer_origins.repository import CustomerOriginRepository
from app.domain.reports.service import ReportsService
from app.domain.stages.repository import StageRepository, StepRepository
from app.domain.task_types.repository import TaskTypeRepository


class ProductivityInput(BaseModel):
    user_id: uuid.UUID | None = Field(
        default=None, description="Omitido = o próprio usuário que perguntou."
    )
    month: date | None = Field(default=None, description="Qualquer dia do mês; padrão: mês atual.")


class BiMetricsInput(BaseModel):
    metric: str = Field(
        default="pipeline",
        description="pipeline | portfolio | conversion — os indicadores das abas de BI.",
    )
    period: date | None = None


class TaxonomiesInput(BaseModel):
    kind: str = Field(
        default="all",
        description="all | action_groups | lawsuit_types | stages | steps | task_types | origins",
    )


class CurrentContextInput(BaseModel):
    """Sem parâmetros: o contexto é o da conversa."""


@tool(
    name="get_productivity",
    description=(
        "Produtividade (Taskscore) de um usuário no mês: tarefas concluídas, pontos, "
        "no prazo e atrasadas. Sem `user_id`, responde sobre quem perguntou."
    ),
)
async def get_productivity(ctx: ToolContext, params: ProductivityInput) -> dict[str, Any]:
    target = params.user_id or ctx.user.id
    # Regra 1: olhar a produtividade DE OUTRA pessoa é privilégio de gestão, igual na
    # tela de relatórios (spec 071).
    if target != ctx.user.id and ctx.user.role not in (
        UserRole.ADMINISTRADOR,
        UserRole.GESTOR,
    ):
        raise ToolError(
            "forbidden",
            "O usuário só pode consultar a própria produtividade. Explique isso a ele.",
        )
    month = (params.month or await ctx.today()).replace(day=1)
    service = ReportsService(session=ctx.session, tenant_id=ctx.tenant_id)
    report = await service.productivity(user_id=target, month=month, today=await ctx.today())
    return {
        "month": month.isoformat(),
        "user_id": str(target),
        "assigned": report.assigned,
        "completed": report.completed,
        "late": report.late,
        "due_in_5_days": report.due_in_5_days,
    }


@tool(
    name="get_bi_metrics",
    description=(
        "Indicadores de BI do escritório: funil de oportunidades (pipeline), carteira "
        "por fase (portfolio) ou conversão do mês (conversion)."
    ),
    requires_role=UserRole.ADMINISTRADOR,
)
async def get_bi_metrics(ctx: ToolContext, params: BiMetricsInput) -> dict[str, Any]:
    service = BiPipelineService(session=ctx.session, tenant_id=ctx.tenant_id)
    today = await ctx.today()
    if params.metric == "pipeline":
        pipeline = await service.pipeline(from_=None, to=None, action_group_id=None, today=today)
        return {
            "metric": "pipeline",
            "opportunities_month": pipeline.opportunities_month,
            "active": pipeline.active,
            "archived": pipeline.archived,
            "idle_120": pipeline.idle_120,
            "in_service": pipeline.in_service,
            "closed_month": pipeline.closed_month.value,
            "staleness_hint": pipeline.staleness_hint,
        }
    if params.metric == "portfolio":
        portfolio = await service.portfolio(group_by="step", action_group_id=None, today=today)
        return {
            "metric": "portfolio",
            "group_by": portfolio.group_by,
            "items": [item.model_dump(mode="json") for item in portfolio.items],
        }
    if params.metric == "conversion":
        conversion = await service.conversion(period=(params.period or today).replace(day=1))
        return {
            "metric": "conversion",
            "groups": [group.model_dump(mode="json") for group in conversion.groups],
        }
    raise ToolError("invalid_argument", "Métrica inválida: use pipeline, portfolio ou conversion.")


@tool(
    name="list_taxonomies",
    description=(
        "Listas de configuração do escritório: grupos de ação, tipos de processo, "
        "fases, etapas, tipos de tarefa e origens. Use para traduzir um nome citado "
        "pelo usuário no id que as outras ferramentas pedem."
    ),
)
async def list_taxonomies(ctx: ToolContext, params: TaxonomiesInput) -> dict[str, Any]:
    wanted = params.kind
    result: dict[str, Any] = {}

    async def include(key: str) -> bool:
        return wanted in ("all", key)

    if await include("action_groups"):
        groups = await ActionGroupRepository(ctx.session).list_filtered(is_active=True)
        result["action_groups"] = [{"id": str(row.id), "name": row.name} for row in groups]
    if await include("lawsuit_types"):
        types = await LawsuitTypeRepository(ctx.session).list_filtered(is_active=True)
        result["lawsuit_types"] = [{"id": str(row.id), "name": row.name} for row in types]
    if await include("stages"):
        stages = await StageRepository(ctx.session).list_filtered(is_active=True)
        result["stages"] = [
            {"id": str(row.id), "name": row.name, "step_id": row.step_id} for row in stages
        ]
    if await include("steps"):
        steps = await StepRepository(ctx.session).list_all()
        result["steps"] = [{"id": row.id, "name": row.name} for row in steps]
    if await include("task_types"):
        task_types = await TaskTypeRepository(ctx.session).list_filtered(
            step_id=None, is_active=True, query=None
        )
        result["task_types"] = [
            {"id": str(row.id), "name": row.name, "reward": row.reward} for row in task_types
        ]
    if await include("origins"):
        origins = await CustomerOriginRepository(ctx.session).list_filtered(is_active=True)
        result["origins"] = [{"id": str(row.id), "name": row.name} for row in origins]
    if not result:
        raise ToolError("invalid_argument", f"Taxonomia desconhecida: {wanted}.")
    return result


@tool(
    name="get_current_context",
    description=(
        "O que está aberto na tela de quem perguntou: processo, cliente ou seção. "
        "Chame primeiro quando o usuário disser 'este processo' ou 'este cliente'."
    ),
)
async def get_current_context(ctx: ToolContext, params: CurrentContextInput) -> dict[str, Any]:
    del params
    return {
        "screen": ctx.screen_context.get("screen"),
        "lawsuit_id": ctx.screen_context.get("lawsuit_id"),
        "customer_id": ctx.screen_context.get("customer_id"),
        "user_name": ctx.user.name,
        "user_role": ctx.user.role.value,
        "has_financial_access": ctx.user.financial_access.value,
    }
