import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http import parse_month_query
from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.reports.schemas import (
    REPORT_KEYS,
    AgilityResponse,
    MostDelayedResponse,
    ProductivityResponse,
    ReportKey,
    ReportListResponse,
    WeeklyChartResponse,
)
from app.domain.reports.service import ReportsService
from app.domain.reports.tabular_service import ReportFilters, TabularReportService
from app.domain.users.models import User

router = APIRouter(prefix="/reports", tags=["reports"])

_DEFAULT_MOST_DELAYED_LIMIT = 10
_DEFAULT_TABULAR_LIMIT = 20

_MIME_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


def _resolve_user_scope(
    current_user: User, requested_user_id: uuid.UUID | None
) -> uuid.UUID | None:
    """Regra 8: Colaborador só vê os próprios números — sem `user_id`, o escopo dele é
    ele mesmo; pedir o `user_id` de outra pessoa é 403. ADMINISTRADOR+ vê todos por
    padrão (`None` = agregado geral) ou filtra por `user_id` à vontade."""
    is_admin = current_user.role in (UserRole.ADMINISTRADOR, UserRole.GESTOR)
    if requested_user_id is not None and requested_user_id != current_user.id and not is_admin:
        raise HTTPException(status_code=403, detail="Você só pode ver os próprios números.")
    if not is_admin:
        return current_user.id
    return requested_user_id


@router.get("/agility")
async def get_agility_report(
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    user_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> AgilityResponse:
    scope_user_id = _resolve_user_scope(current_user, user_id)
    end = to or date.today()
    start = from_ or end.replace(day=1)
    service = ReportsService(session=session, tenant_id=current_user.tenant_id)
    return await service.agility(user_id=scope_user_id, start=start, end=end)


@router.get("/productivity")
async def get_productivity_report(
    month: str | None = Query(default=None),
    user_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> ProductivityResponse:
    scope_user_id = _resolve_user_scope(current_user, user_id)
    month_start = parse_month_query(month)
    service = ReportsService(session=session, tenant_id=current_user.tenant_id)
    return await service.productivity(user_id=scope_user_id, month=month_start)


@router.get("/productivity/weekly")
async def get_productivity_weekly_report(
    user_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> WeeklyChartResponse:
    scope_user_id = _resolve_user_scope(current_user, user_id)
    service = ReportsService(session=session, tenant_id=current_user.tenant_id)
    return await service.productivity_weekly(user_id=scope_user_id, today=date.today())


@router.get("/most-delayed")
async def get_most_delayed_report(
    limit: int = Query(default=_DEFAULT_MOST_DELAYED_LIMIT, ge=1, le=100),
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> MostDelayedResponse:
    service = ReportsService(session=session, tenant_id=current_user.tenant_id)
    return await service.most_delayed(limit=limit)


# ---- relatórios tabulares (spec 072) -------------------------------------------
#
# Nota (spec 072 Descobertas): a spec descreve a rota genérica como
# `GET /api/v1/reports/{report_key}`, mas "productivity" colide com o endpoint
# agregado de 071 (`/reports/productivity`, já em produção) — mesmo path, formas de
# resposta incompatíveis. Resolvido montando os 9 relatórios tabulares sob
# `/reports/tabular/{report_key}`, preservando os 071 exatamente como estavam.


def _resolve_tabular_scope(
    current_user: User, report_key: ReportKey, requested_user_id: uuid.UUID | None
) -> uuid.UUID | None:
    """Regra 11: todos exigem ADMINISTRADOR, exceto `productivity`, onde o Colaborador
    vê só os próprios dados — mesmo idioma de `_resolve_user_scope` (071)."""
    is_admin = current_user.role in (UserRole.ADMINISTRADOR, UserRole.GESTOR)
    if report_key != "productivity":
        if not is_admin:
            raise HTTPException(status_code=403, detail="Exige perfil ADMINISTRADOR ou superior.")
        return requested_user_id
    if requested_user_id is not None and requested_user_id != current_user.id and not is_admin:
        raise HTTPException(status_code=403, detail="Você só pode ver os próprios dados.")
    if not is_admin:
        return current_user.id
    return requested_user_id


@router.get("/tabular/{report_key}")
async def get_tabular_report(
    report_key: ReportKey,
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    user_id: uuid.UUID | None = Query(default=None),
    action_group_id: uuid.UUID | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_TABULAR_LIMIT, ge=1, le=100),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> ReportListResponse:
    if report_key not in REPORT_KEYS:
        raise HTTPException(status_code=404, detail="Relatório desconhecido.")
    scope_user_id = _resolve_tabular_scope(current_user, report_key, user_id)
    filters = ReportFilters(
        from_=from_, to=to, user_id=scope_user_id, action_group_id=action_group_id
    )
    service = TabularReportService(session=session, tenant_id=current_user.tenant_id)
    return await service.fetch(report_key, filters, cursor=cursor, limit=limit)


@router.post("/tabular/{report_key}/export")
async def export_tabular_report(
    report_key: ReportKey,
    format_: Literal["xlsx", "pdf"] = Query(alias="format"),
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    user_id: uuid.UUID | None = Query(default=None),
    action_group_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> Response:
    if report_key not in REPORT_KEYS:
        raise HTTPException(status_code=404, detail="Relatório desconhecido.")
    scope_user_id = _resolve_tabular_scope(current_user, report_key, user_id)
    filters = ReportFilters(
        from_=from_, to=to, user_id=scope_user_id, action_group_id=action_group_id
    )
    service = TabularReportService(session=session, tenant_id=current_user.tenant_id)
    content = await service.export(report_key, filters, format_=format_)
    return Response(content=content, media_type=_MIME_TYPES[format_])
