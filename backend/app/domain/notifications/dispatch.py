"""Ponto único de disparo de evento (spec 069) — resolve a regra do tenant, cria a
notificação in-app (regra 3) e manda pelos canais configurados respeitando a
preferência do usuário (regra 4), sempre best-effort (regra 5: canal quebrado nunca
derruba quem chamou)."""

import contextlib
import uuid
from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.notifications.models import NotificationChannelName, NotificationEvent
from app.domain.notifications.repository import (
    NotificationRuleRepository,
    UserNotificationPreferenceRepository,
)
from app.domain.notifications.service import NotificationService
from app.domain.users.models import User
from app.integrations.messaging.base import MessagingChannel


class NotificationDispatcher:
    def __init__(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        channels: Mapping[str, MessagingChannel] | None = None,
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.channels = channels or {}
        self.rules = NotificationRuleRepository(session)
        self.preferences = UserNotificationPreferenceRepository(session)
        self.notifications = NotificationService(session, tenant_id)

    async def dispatch(
        self, event: NotificationEvent, *, title: str, body: str, link: str | None = None
    ) -> None:
        rule = await self.rules.get_by_event(event)
        # Regra 1/2: sem regra ("não configurado") ou responsável nulo ("não
        # notificar") — os dois não fazem nada, in-app nem canal.
        if rule is None or rule.responsible_user_id is None:
            return

        await self.notifications.notify(
            user_id=rule.responsible_user_id, kind=event.value, title=title, body=body, link=link
        )

        if not rule.channels or not self.channels:
            return

        user = await self.session.get(User, rule.responsible_user_id)
        if user is None:
            return

        for channel_name in rule.channels:
            channel = self.channels.get(channel_name)
            if channel is None:
                continue
            preference = await self.preferences.get(
                rule.responsible_user_id, NotificationChannelName(channel_name)
            )
            if preference is not None and not preference.enabled:
                continue
            to = user.email if channel_name == "EMAIL" else user.cellphone
            if not to:
                continue
            with contextlib.suppress(Exception):
                await channel.send(to=to, subject=title, message=body)
