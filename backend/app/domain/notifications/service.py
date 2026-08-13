import uuid
from datetime import UTC, datetime

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.notifications.models import (
    Notification,
    NotificationChannelName,
    NotificationEvent,
    NotificationRule,
    UserNotificationPreference,
)
from app.domain.notifications.repository import (
    NotificationRepository,
    NotificationRuleRepository,
    UserNotificationPreferenceRepository,
)


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


class NotificationRuleResponse(BaseModel):
    event: NotificationEvent
    responsible_user_id: uuid.UUID | None
    channels: list[NotificationChannelName]


class NotificationRuleUpdateRequest(BaseModel):
    responsible_user_id: uuid.UUID | None = None
    channels: list[NotificationChannelName] = []


class NotificationRuleService:
    """Config por evento (spec 069) — sempre devolve as 3 linhas do catálogo
    (regra 1: evento sem regra salva ainda aparece, com responsável nulo/canais
    vazios, pra UI não ter que saber quais eventos existem)."""

    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.tenant_id = tenant_id
        self.rules = NotificationRuleRepository(session)

    async def list_all(self) -> list[NotificationRuleResponse]:
        existing = {rule.event: rule for rule in await self.rules.list_all()}
        return [
            NotificationRuleResponse(
                event=event,
                responsible_user_id=(
                    existing[event].responsible_user_id if event in existing else None
                ),
                channels=(
                    [NotificationChannelName(c) for c in existing[event].channels]
                    if event in existing
                    else []
                ),
            )
            for event in NotificationEvent
        ]

    async def upsert(
        self, event: NotificationEvent, data: NotificationRuleUpdateRequest
    ) -> NotificationRuleResponse:
        rule = await self.rules.get_by_event(event)
        channel_values = [channel.value for channel in data.channels]
        if rule is None:
            rule = await self.rules.create(
                NotificationRule(
                    tenant_id=self.tenant_id,
                    event=event,
                    responsible_user_id=data.responsible_user_id,
                    channels=channel_values,
                )
            )
        else:
            rule.responsible_user_id = data.responsible_user_id
            rule.channels = channel_values
            rule.updated_at = datetime.now(UTC)
        return NotificationRuleResponse(
            event=rule.event,
            responsible_user_id=rule.responsible_user_id,
            channels=[NotificationChannelName(c) for c in rule.channels],
        )


class NotificationPreferenceResponse(BaseModel):
    channel: NotificationChannelName
    enabled: bool


class NotificationPreferenceUpdateRequest(BaseModel):
    enabled: bool


class UserNotificationPreferenceService:
    """Liga/desliga canal por usuário (spec 069, regra 7) — sempre devolve os 3
    canais, habilitados por padrão quando não há registro."""

    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.tenant_id = tenant_id
        self.preferences = UserNotificationPreferenceRepository(session)

    async def list_for_user(self, user_id: uuid.UUID) -> list[NotificationPreferenceResponse]:
        existing = {pref.channel: pref for pref in await self.preferences.list_for_user(user_id)}
        return [
            NotificationPreferenceResponse(
                channel=channel,
                enabled=existing[channel].enabled if channel in existing else True,
            )
            for channel in NotificationChannelName
        ]

    async def upsert(
        self,
        user_id: uuid.UUID,
        channel: NotificationChannelName,
        data: NotificationPreferenceUpdateRequest,
    ) -> NotificationPreferenceResponse:
        preference = await self.preferences.get(user_id, channel)
        if preference is None:
            preference = await self.preferences.create(
                UserNotificationPreference(
                    tenant_id=self.tenant_id, user_id=user_id, channel=channel, enabled=data.enabled
                )
            )
        else:
            preference.enabled = data.enabled
        return NotificationPreferenceResponse(
            channel=preference.channel, enabled=preference.enabled
        )
