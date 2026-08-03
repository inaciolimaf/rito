import uuid
from datetime import UTC, datetime

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.notifications.models import Notification
from app.domain.notifications.repository import NotificationRepository


class NotificationResponse(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    body: str | None
    link: str | None
    read_at: datetime | None
    created_at: datetime


class NotificationPage(BaseModel):
    """Contrato de listagem do CLAUDE.md §6 — keyset, nunca offset."""

    items: list[NotificationResponse]
    next_cursor: str | None
    total: int


class NotificationService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.notifications = NotificationRepository(session)

    async def notify(
        self,
        *,
        user_id: uuid.UUID,
        kind: str,
        title: str,
        body: str | None = None,
        link: str | None = None,
    ) -> Notification:
        """Ponto único de criação — quem chama (menções hoje; prazos, atribuições e IA
        amanhã) não conhece a tabela."""
        return await self.notifications.create_notification(
            tenant_id=self.tenant_id,
            user_id=user_id,
            kind=kind,
            title=title,
            body=body,
            link=link,
        )

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        unread_only: bool,
        cursor: tuple[datetime, uuid.UUID] | None,
        limit: int,
    ) -> tuple[list[Notification], int, bool]:
        rows = list(
            await self.notifications.list_for_user(
                user_id, unread_only=unread_only, cursor=cursor, limit=limit
            )
        )
        total = await self.notifications.count_for_user(user_id, unread_only=unread_only)
        has_more = len(rows) > limit
        return rows[:limit], total, has_more

    async def mark_read(
        self, notification_id: uuid.UUID, user_id: uuid.UUID
    ) -> Notification | None:
        notification = await self.notifications.get_by_id(notification_id)
        # Só o dono lê a própria notificação — para os demais é 404 (existir já é
        # informação, mesmo padrão da tarefa privada).
        if notification is None or notification.user_id != user_id:
            return None
        await self.notifications.mark_read(notification, datetime.now(UTC))
        return notification

    async def mark_all_read(self, user_id: uuid.UUID) -> int:
        return await self.notifications.mark_all_read(user_id, datetime.now(UTC))
