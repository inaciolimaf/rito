import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, literal, select, tuple_, update

from app.core.repository import BaseRepository
from app.domain.notifications.models import (
    Notification,
    NotificationChannelName,
    NotificationEvent,
    NotificationRule,
    UserNotificationPreference,
)


class NotificationRepository(BaseRepository[Notification]):
    model = Notification

    async def create_notification(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        kind: str,
        title: str,
        body: str | None,
        link: str | None,
    ) -> Notification:
        """Assinatura própria (não sobrepõe BaseRepository.create — kwargs de domínio
        em vez da instância pronta)."""
        notification = Notification(
            tenant_id=tenant_id,
            user_id=user_id,
            kind=kind,
            title=title,
            body=body,
            link=link,
        )
        self.session.add(notification)
        await self.session.flush()
        return notification

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        unread_only: bool,
        cursor: tuple[datetime, uuid.UUID] | None,
        limit: int,
    ) -> Sequence[Notification]:
        """Keyset DESC por (created_at, id) — a mais nova primeiro (sino do header).
        Cursor manual porque build_sorted_keyset_query é ASC-only."""
        stmt = (
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(limit + 1)
        )
        if unread_only:
            stmt = stmt.where(Notification.read_at.is_(None))
        if cursor is not None:
            cursor_value, cursor_id = cursor
            stmt = stmt.where(
                tuple_(Notification.created_at, Notification.id)
                < tuple_(literal(cursor_value), literal(cursor_id))
            )
        return (await self.session.scalars(stmt)).all()

    async def count_for_user(self, user_id: uuid.UUID, *, unread_only: bool) -> int:
        stmt = select(func.count()).select_from(Notification).where(Notification.user_id == user_id)
        if unread_only:
            stmt = stmt.where(Notification.read_at.is_(None))
        return int((await self.session.execute(stmt)).scalar_one())

    async def mark_read(self, notification: Notification, when: datetime) -> None:
        if notification.read_at is None:
            notification.read_at = when
            await self.session.flush()

    async def mark_all_read(self, user_id: uuid.UUID, when: datetime) -> int:
        result = await self.session.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
            .values(read_at=when)
            .execution_options(synchronize_session=False)
        )
        return int(result.rowcount)  # type: ignore[attr-defined]


class NotificationRuleRepository(BaseRepository[NotificationRule]):
    model = NotificationRule

    async def get_by_event(self, event: NotificationEvent) -> NotificationRule | None:
        stmt = select(NotificationRule).where(NotificationRule.event == event)
        result: NotificationRule | None = await self.session.scalar(stmt)
        return result

    async def list_all(self) -> Sequence[NotificationRule]:
        stmt = select(NotificationRule).order_by(NotificationRule.event)
        return (await self.session.scalars(stmt)).all()


class UserNotificationPreferenceRepository(BaseRepository[UserNotificationPreference]):
    model = UserNotificationPreference

    async def get(
        self, user_id: uuid.UUID, channel: NotificationChannelName
    ) -> UserNotificationPreference | None:
        stmt = select(UserNotificationPreference).where(
            UserNotificationPreference.user_id == user_id,
            UserNotificationPreference.channel == channel,
        )
        result: UserNotificationPreference | None = await self.session.scalar(stmt)
        return result

    async def list_for_user(self, user_id: uuid.UUID) -> Sequence[UserNotificationPreference]:
        stmt = select(UserNotificationPreference).where(
            UserNotificationPreference.user_id == user_id
        )
        return (await self.session.scalars(stmt)).all()
