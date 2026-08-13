import base64
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.notifications.models import Notification, NotificationChannelName, NotificationEvent
from app.domain.notifications.service import (
    NotificationPage,
    NotificationPreferenceResponse,
    NotificationPreferenceUpdateRequest,
    NotificationResponse,
    NotificationRuleResponse,
    NotificationRuleService,
    NotificationRuleUpdateRequest,
    NotificationService,
    UserNotificationPreferenceService,
)
from app.domain.users.models import User

router = APIRouter(tags=["notifications"])

_SEPARATOR = "\x1f"


def _encode_cursor(notification: Notification) -> str:
    raw = f"{notification.created_at.isoformat()}{_SEPARATOR}{notification.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    value, _, id_str = raw.rpartition(_SEPARATOR)
    return datetime.fromisoformat(value), uuid.UUID(id_str)


def _to_response(notification: Notification) -> NotificationResponse:
    return NotificationResponse(
        id=notification.id,
        kind=notification.kind,
        title=notification.title,
        body=notification.body,
        link=notification.link,
        read_at=notification.read_at,
        created_at=notification.created_at,
    )


@router.get("/notifications")
async def list_notifications(
    unread: bool = Query(default=False),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> NotificationPage:
    service = NotificationService(session=session, tenant_id=current_user.tenant_id)
    decoded = _decode_cursor(cursor) if cursor else None
    items, total, has_more = await service.list_for_user(
        current_user.id, unread_only=unread, cursor=decoded, limit=limit
    )
    return NotificationPage(
        items=[_to_response(item) for item in items],
        next_cursor=_encode_cursor(items[-1]) if has_more and items else None,
        total=total,
    )


@router.post("/notifications/{notification_id}/read")
async def read_notification(
    notification_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> NotificationResponse:
    service = NotificationService(session=session, tenant_id=current_user.tenant_id)
    notification = await service.mark_read(notification_id, current_user.id)
    if notification is None:
        raise HTTPException(status_code=404, detail="Notificação não encontrada.")
    return _to_response(notification)


@router.post("/notifications/read-all")
async def read_all_notifications(
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> dict[str, int]:
    service = NotificationService(session=session, tenant_id=current_user.tenant_id)
    updated = await service.mark_all_read(current_user.id)
    return {"updated": updated}


@router.get("/notification-rules")
async def list_notification_rules(
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> list[NotificationRuleResponse]:
    service = NotificationRuleService(session=session, tenant_id=current_user.tenant_id)
    return await service.list_all()


@router.put("/notification-rules/{event}")
async def update_notification_rule(
    event: NotificationEvent,
    payload: NotificationRuleUpdateRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> NotificationRuleResponse:
    service = NotificationRuleService(session=session, tenant_id=current_user.tenant_id)
    return await service.upsert(event, payload)


@router.get("/notification-preferences")
async def list_notification_preferences(
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> list[NotificationPreferenceResponse]:
    service = UserNotificationPreferenceService(session=session, tenant_id=current_user.tenant_id)
    return await service.list_for_user(current_user.id)


@router.put("/notification-preferences/{channel}")
async def update_notification_preference(
    channel: NotificationChannelName,
    payload: NotificationPreferenceUpdateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> NotificationPreferenceResponse:
    service = UserNotificationPreferenceService(session=session, tenant_id=current_user.tenant_id)
    return await service.upsert(current_user.id, channel, payload)
