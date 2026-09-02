import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.integration_alerts.schemas import (
    IntegrationAlertListResponse,
    IntegrationAlertResponse,
)
from app.domain.integration_alerts.service import IntegrationAlertService
from app.domain.integrations.schemas import (
    IntegrationStatusItemResponse,
    IntegrationStatusResponse,
    TermsByStatusItemResponse,
)
from app.domain.integrations.service import IntegrationStatusService
from app.domain.users.models import User

router = APIRouter(prefix="/integrations", tags=["integrations"])

_NOT_FOUND_DETAIL = "Alerta não encontrado."


@router.get("/status")
async def get_integration_status(
    _current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> IntegrationStatusResponse:
    status = await IntegrationStatusService(session).get_status()
    return IntegrationStatusResponse(
        integrations=[
            IntegrationStatusItemResponse(
                integration=item.integration,
                is_healthy=item.is_healthy,
                last_success_at=item.last_success_at,
                avg_latency_ms=item.avg_latency_ms,
                failures_24h=item.failures_24h,
            )
            for item in status.integrations
        ],
        terms_by_status=[
            TermsByStatusItemResponse(status=item.status, count=item.count)
            for item in status.terms_by_status
        ],
    )


@router.get("/alerts")
async def list_integration_alerts(
    resolved: bool | None = Query(default=None),
    _current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> IntegrationAlertListResponse:
    alerts = list(await IntegrationAlertService(session).list_filtered(resolved=resolved))
    return IntegrationAlertListResponse(
        items=[
            IntegrationAlertResponse(
                id=alert.id,
                integration=alert.integration,
                severity=alert.severity,
                code=alert.code,
                message=alert.message,
                responsible_user_id=alert.responsible_user_id,
                resolved_at=alert.resolved_at,
                resolved_by=alert.resolved_by,
                created_at=alert.created_at,
            )
            for alert in alerts
        ],
        total=len(alerts),
    )


@router.post("/alerts/{alert_id}/resolve")
async def resolve_integration_alert(
    alert_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> IntegrationAlertResponse:
    service = IntegrationAlertService(session)
    alert = await service.get(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)
    await service.resolve(alert, resolved_by=current_user.id)
    return IntegrationAlertResponse(
        id=alert.id,
        integration=alert.integration,
        severity=alert.severity,
        code=alert.code,
        message=alert.message,
        responsible_user_id=alert.responsible_user_id,
        resolved_at=alert.resolved_at,
        resolved_by=alert.resolved_by,
        created_at=alert.created_at,
    )
