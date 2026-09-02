"""Ponto único de disparo de evento (spec 069) — resolve a regra do tenant, cria a
notificação in-app (regra 3) e manda pelos canais configurados respeitando a
preferência do usuário (regra 4), sempre best-effort (regra 5: canal quebrado nunca
derruba quem chamou)."""

import contextlib
import uuid
from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.invariants import not_none
from app.domain.notifications.models import (
    NotificationChannelName,
    NotificationEvent,
    NotificationRule,
)
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
            await self._enviar_por_canal(channel_name, user=user, rule=rule, title=title, body=body)

    async def _enviar_por_canal(
        self,
        channel_name: str,
        *,
        user: User,
        rule: NotificationRule,
        title: str,
        body: str,
    ) -> None:
        """Um canal, para um destinatário. Três razões para não enviar, todas silenciosas:
        canal não configurado no servidor, preferência do usuário desligada, ou destino
        vazio (e-mail/celular em branco no cadastro).

        A falha do envio também é engolida de propósito: notificação é acessório do que
        acabou de acontecer, e derrubar a operação principal porque o SMS não saiu seria
        trocar um aviso perdido por um trabalho perdido.
        """
        channel = self.channels.get(channel_name)
        if channel is None:
            return
        responsavel = not_none(
            rule.responsible_user_id, "regra com canal definido sempre tem responsável"
        )
        preference = await self.preferences.get(responsavel, NotificationChannelName(channel_name))
        if preference is not None and not preference.enabled:
            return
        to = user.email if channel_name == "EMAIL" else user.cellphone
        if not to:
            return
        with contextlib.suppress(Exception):
            await channel.send(to=to, subject=title, message=body)
