from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.integration_alerts.repository import IntegrationAlertRepository
from app.domain.integration_alerts.schemas import (
    IntegrationAlertListResponse,
    IntegrationAlertResponse,
)
from app.domain.users.models import User

router = APIRouter(prefix="/integration-alerts", tags=["integration-alerts"])


@router.get("")
async def list_open_alerts(
    _current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> IntegrationAlertListResponse:
    """Alertas abertos — o `IntegrationAlertBanner` do front consome isso direto
    (spec 046 §6). RLS libera as linhas de sistema (`tenant_id` nulo) para
    qualquer tenant e isola as tenant-específicas (migration 046)."""
    alerts = list(await IntegrationAlertRepository(session).list_open())
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
