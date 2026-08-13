"""Notificações: motor de disparo (spec 069, §4) — sem regra não faz nada, com regra
cria o in-app e tenta os canais configurados respeitando a preferência do usuário,
sempre best-effort (canal quebrado não derruba quem chamou)."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.notifications.dispatch import NotificationDispatcher
from app.domain.notifications.models import (
    NotificationChannelName,
    NotificationEvent,
    NotificationRule,
    UserNotificationPreference,
)
from app.domain.notifications.repository import NotificationRepository
from app.integrations.messaging.base import MessagingChannel
from tests.integration.conftest import SeededUser


@dataclass
class SentMessage:
    to: str
    subject: str
    message: str


class FakeEmailChannel:
    def __init__(self) -> None:
        self.sent: list[SentMessage] = []

    async def send(self, *, to: str, subject: str, message: str) -> None:
        self.sent.append(SentMessage(to=to, subject=subject, message=message))


class BrokenChannel:
    async def send(self, *, to: str, subject: str, message: str) -> None:
        raise RuntimeError("provider fora do ar")


async def _dispatch(
    session_factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    channels: dict[str, MessagingChannel],
    *,
    event: NotificationEvent,
    title: str,
    body: str,
) -> None:
    async with session_factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        dispatcher = NotificationDispatcher(session=session, tenant_id=tenant_id, channels=channels)
        await dispatcher.dispatch(event, title=title, body=body)


async def test_sem_regra_nao_faz_nada(
    app_session_factory: async_sessionmaker[AsyncSession],
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    seeded = await make_user()
    await _dispatch(
        app_session_factory,
        seeded.tenant_id,
        {},
        event=NotificationEvent.NOVO_CLIENTE,
        title="t",
        body="b",
    )

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, seeded.tenant_id)
        notifications = await NotificationRepository(session).list_for_user(
            seeded.user_id, unread_only=False, cursor=None, limit=10
        )
    assert notifications == []


async def test_responsavel_nulo_nao_notifica(
    app_session_factory: async_sessionmaker[AsyncSession],
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    seeded = await make_user()
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, seeded.tenant_id)
        session.add(
            NotificationRule(
                tenant_id=seeded.tenant_id,
                event=NotificationEvent.NOVO_CLIENTE,
                responsible_user_id=None,
                channels=[],
            )
        )

    await _dispatch(
        app_session_factory,
        seeded.tenant_id,
        {},
        event=NotificationEvent.NOVO_CLIENTE,
        title="t",
        body="b",
    )

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, seeded.tenant_id)
        notifications = await NotificationRepository(session).list_for_user(
            seeded.user_id, unread_only=False, cursor=None, limit=10
        )
    assert notifications == []


async def test_regra_com_canal_cria_in_app_e_envia_email(
    app_session_factory: async_sessionmaker[AsyncSession],
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    seeded = await make_user()
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, seeded.tenant_id)
        session.add(
            NotificationRule(
                tenant_id=seeded.tenant_id,
                event=NotificationEvent.NOVO_CLIENTE,
                responsible_user_id=seeded.user_id,
                channels=["EMAIL"],
            )
        )

    email_channel = FakeEmailChannel()
    await _dispatch(
        app_session_factory,
        seeded.tenant_id,
        {"EMAIL": email_channel},
        event=NotificationEvent.NOVO_CLIENTE,
        title="Novo contato cadastrado",
        body="Maria da Silva",
    )

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, seeded.tenant_id)
        notifications = await NotificationRepository(session).list_for_user(
            seeded.user_id, unread_only=False, cursor=None, limit=10
        )
    assert len(notifications) == 1
    assert notifications[0].title == "Novo contato cadastrado"
    assert len(email_channel.sent) == 1
    assert email_channel.sent[0].to == seeded.email


async def test_preferencia_desabilitada_pula_o_canal(
    app_session_factory: async_sessionmaker[AsyncSession],
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    seeded = await make_user()
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, seeded.tenant_id)
        session.add(
            NotificationRule(
                tenant_id=seeded.tenant_id,
                event=NotificationEvent.NOVO_CLIENTE,
                responsible_user_id=seeded.user_id,
                channels=["EMAIL"],
            )
        )
        session.add(
            UserNotificationPreference(
                tenant_id=seeded.tenant_id,
                user_id=seeded.user_id,
                channel=NotificationChannelName.EMAIL,
                enabled=False,
            )
        )

    email_channel = FakeEmailChannel()
    await _dispatch(
        app_session_factory,
        seeded.tenant_id,
        {"EMAIL": email_channel},
        event=NotificationEvent.NOVO_CLIENTE,
        title="t",
        body="b",
    )

    assert email_channel.sent == []


async def test_canal_sem_provider_nao_quebra_o_fluxo(
    app_session_factory: async_sessionmaker[AsyncSession],
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    seeded = await make_user()
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, seeded.tenant_id)
        session.add(
            NotificationRule(
                tenant_id=seeded.tenant_id,
                event=NotificationEvent.NOVO_CLIENTE,
                responsible_user_id=seeded.user_id,
                channels=["EMAIL"],
            )
        )

    # Sem levantar exceção mesmo com o canal quebrado (regra 5: best-effort).
    await _dispatch(
        app_session_factory,
        seeded.tenant_id,
        {"EMAIL": BrokenChannel()},
        event=NotificationEvent.NOVO_CLIENTE,
        title="t",
        body="b",
    )

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, seeded.tenant_id)
        notifications = await NotificationRepository(session).list_for_user(
            seeded.user_id, unread_only=False, cursor=None, limit=10
        )
    assert len(notifications) == 1
