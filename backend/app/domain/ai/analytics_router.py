"""Rotas da IA analítica (spec 089 §6).

`ask` é deliberadamente em **duas etapas**: uma chamada gera e valida o SQL, e o
usuário decide se roda (regra 3). Juntar as duas numa só economizaria um clique e
tiraria da pessoa a única chance de olhar o que vai ser executado.
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock
from app.core.http import get_or_404
from app.core.permissions import UserRole, require_role
from app.domain.ai.analytics import (
    AnalyticsService,
    ClarificationNeeded,
    NextAction,
    SqlRejected,
)
from app.domain.ai.exceptions import FeatureDisabledError
from app.domain.ai.models import AiInsight
from app.domain.ai.router import get_llm_provider
from app.domain.ai.service import AiRunner
from app.domain.ai.sql_guard import check_sql
from app.domain.auth.deps import get_clock, get_session_for_current_user
from app.domain.users.models import FinancialAccess, User
from app.integrations.openrouter.types import LLMNotConfiguredError, LLMProvider

logger = logging.getLogger("rito.ai.analytics")

router = APIRouter(prefix="/ai", tags=["ai"])
lawsuits_router = APIRouter(prefix="/lawsuits", tags=["ai"])

_UNAVAILABLE = "A IA analítica não está disponível neste escritório."


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    # Segunda etapa: o SQL que o usuário viu e aprovou (regra 3).
    confirm_sql: str | None = None


class AskResponse(BaseModel):
    sql: str
    relations: list[str]
    touches_financial: bool
    # Preenchidos só depois de confirmar.
    executed: bool = False
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    summary: str | None = None
    query_id: uuid.UUID | None = None


class InsightResponse(BaseModel):
    id: uuid.UUID
    kind: str
    severity: str
    subject_type: str | None
    subject_id: uuid.UUID | None
    title: str
    body: str
    suggested_action: dict[str, Any] | None
    dismissed_at: datetime | None
    created_at: datetime


class InsightListResponse(BaseModel):
    items: list[InsightResponse]
    total: int


class NextActionResponse(BaseModel):
    lawsuit_id: uuid.UUID
    action: str
    reason: str
    signals: dict[str, Any]
    # Regra 7: virar tarefa é pelo fluxo de aprovação da 084, nunca direto.
    suggested_tool: str | None
    suggested_arguments: dict[str, Any]


class RefreshResponse(BaseModel):
    created: int


def _service(session: AsyncSession, user: User, provider: LLMProvider) -> AnalyticsService:
    return AnalyticsService(
        session=session,
        tenant_id=user.tenant_id,
        runner=AiRunner(session, user.tenant_id, provider),
    )


def _to_insight(insight: AiInsight) -> InsightResponse:
    return InsightResponse(
        id=insight.id,
        kind=insight.kind,
        severity=insight.severity,
        subject_type=insight.subject_type,
        subject_id=insight.subject_id,
        title=insight.title,
        body=insight.body,
        suggested_action=insight.suggested_action,
        dismissed_at=insight.dismissed_at,
        created_at=insight.created_at,
    )


def _to_next_action(lawsuit_id: uuid.UUID, action: NextAction) -> NextActionResponse:
    return NextActionResponse(
        lawsuit_id=lawsuit_id,
        action=action.action,
        reason=action.reason,
        signals=action.signals,
        suggested_tool=action.suggested_tool,
        suggested_arguments=action.suggested_arguments,
    )


@router.post("/analytics/ask")
async def ask_metrics(
    payload: AskRequest,
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> AskResponse:
    """Regra 5: text-to-SQL é de ADMINISTRADOR para cima; o recorte financeiro ainda
    exige acesso financeiro, e quem barra isso é o guardrail."""
    service = _service(session, current_user, provider)
    try:
        if payload.confirm_sql is None:
            checado = await service.generate_sql(payload.question, user=current_user)
            return AskResponse(
                sql=checado.sql,
                relations=checado.relations,
                touches_financial=checado.touches_financial,
            )
        # Na confirmação, o SQL passa pelo guardrail DE NOVO: o cliente pode ter mexido
        # no texto entre uma chamada e outra.
        checado = check_sql(
            payload.confirm_sql,
            has_financial_access=current_user.financial_access != FinancialAccess.NONE,
        )
    except ClarificationNeeded as exc:
        # Convenção do projeto (app/core/errors.py): chaves extras no `detail` viram
        # membros de extensão do problem+json — é assim que a dúvida chega à tela sem
        # inventar um formato de erro novo.
        raise HTTPException(
            status_code=422,
            detail={
                "detail": "Preciso de um esclarecimento antes de consultar.",
                "clarification": exc.question,
            },
        ) from exc
    except SqlRejected as exc:
        raise HTTPException(status_code=422, detail=exc.reason) from exc
    except (LLMNotConfiguredError, FeatureDisabledError) as exc:
        raise HTTPException(status_code=409, detail=_UNAVAILABLE) from exc

    try:
        resultado = await service.run_sql(
            user=current_user, question=payload.question, checked=checado
        )
    except Exception as exc:
        logger.warning("Consulta analítica falhou: %s: %s", type(exc).__name__, exc)
        raise HTTPException(
            status_code=422,
            detail="A consulta não pôde ser executada (tempo limite ou erro de sintaxe).",
        ) from exc
    return AskResponse(
        sql=resultado.sql,
        relations=checado.relations,
        touches_financial=checado.touches_financial,
        executed=True,
        columns=resultado.columns,
        rows=resultado.rows,
        summary=resultado.summary,
        query_id=resultado.query.id,
    )


@router.get("/insights")
async def list_insights(
    kind: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    dismissed: bool = Query(default=False),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> InsightListResponse:
    service = _service(session, current_user, provider)
    rows = list(await service.insights.list_open(kind=kind, severity=severity, dismissed=dismissed))
    return InsightListResponse(items=[_to_insight(row) for row in rows], total=len(rows))


@router.post("/insights/{insight_id}/dismiss")
async def dismiss_insight(
    insight_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> InsightResponse:
    """Regra 10: dispensar silencia aquele assunto por 30 dias."""
    service = _service(session, current_user, provider)
    insight = await get_or_404(
        lambda: service.insights.get_by_id(insight_id), "Insight não encontrado."
    )
    return _to_insight(await service.dismiss(insight, user=current_user))


@router.post("/insights/refresh")
async def refresh_insights(
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
    clock: Clock = Depends(get_clock),
) -> RefreshResponse:
    service = _service(session, current_user, provider)
    return RefreshResponse(created=await service.refresh_insights(today=clock.today()))


@lawsuits_router.get("/{lawsuit_id}/next-best-action")
async def get_next_best_action(
    lawsuit_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
    clock: Clock = Depends(get_clock),
) -> NextActionResponse:
    """Regra 6: a recomendação é calculada por regra sobre os sinais do processo — sem
    modelo, sem custo por consulta e igual toda vez que os dados forem iguais."""
    service = _service(session, current_user, provider)
    try:
        acao = await service.next_best_action(lawsuit_id, today=clock.today())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Processo não encontrado.") from exc
    return _to_next_action(lawsuit_id, acao)
