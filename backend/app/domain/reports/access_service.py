"""Livro de ponto e registro de acesso (spec 073) — orquestração das regras 4-8: a
jornada aparente vem do primeiro/último acesso do dia; o desvio compara o primeiro
acesso (convertido para o timezone da conta) com `work_start` do usuário; dia sem
acesso não gera linha "zerada" — não presume falta."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dates import month_end
from app.core.repository import decode_cursor, encode_cursor
from app.domain.account.models import Account
from app.domain.account.repository import AccountRepository
from app.domain.reports.access_repository import AccessLogRepository
from app.domain.reports.models import TimesheetDay
from app.domain.users.models import User
from app.domain.workflows.repository import HolidayRepository


@dataclass
class AccessLogItem:
    log_id: uuid.UUID
    user_name: str
    ip_address: str | None
    occurred_at: datetime


# Âncora arbitrária: os dois horários são combinados com a MESMA data e subtraídos, então
# o dia se cancela e o resultado só depende das horas. Era `date.today()` — o que dava a
# entender que o dia importava, e ainda fazia o cálculo depender do fuso do servidor sem
# necessidade nenhuma (spec 114).
_ANCHOR = date(2000, 1, 1)


def _deviation_minutes(first_access_local: time, work_start: time) -> int:
    delta = datetime.combine(_ANCHOR, first_access_local) - datetime.combine(_ANCHOR, work_start)
    return int(delta.total_seconds() // 60)


class AccessLogService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.repo = AccessLogRepository(session)
        self.holidays = HolidayRepository(session)
        self.accounts = AccountRepository(session)

    async def get_account(self) -> Account | None:
        """A conta do escritório — o livro de ponto depende do fuso dela (regra 5).

        Vinha lida no router direto do `AccountRepository` (spec 118, checagem 2). Quem
        decide o que fazer quando ela não existe continua sendo o router: aqui é `None`,
        lá é 404.
        """
        return await self.accounts.get_current()

    async def list_access_logs(
        self,
        *,
        user_id: uuid.UUID | None,
        from_: date | None,
        to: date | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[AccessLogItem], str | None, int]:
        decoded = None
        if cursor is not None:
            raw_value, id_ = decode_cursor(cursor)
            decoded = (datetime.fromisoformat(raw_value), id_)
        rows, total = await self.repo.list_raw_logs(
            user_id=user_id, from_=from_, to=to, cursor=decoded, limit=limit
        )
        items = [
            AccessLogItem(log_id=row[0], user_name=row[1], ip_address=row[2], occurred_at=row[3])
            for row in rows
        ]
        # Codificar o cursor é simétrico a decodificá-lo, e as duas metades ficam na
        # mesma camada (spec 118, checagem 2): o router só repassa a string opaca.
        next_cursor = (
            encode_cursor(items[-1].occurred_at.isoformat(), items[-1].log_id)
            if len(items) == limit
            else None
        )
        return items, next_cursor, total

    async def timesheet(
        self, *, user: User, account: Account, month_start: date
    ) -> list[TimesheetDay]:
        end = month_end(month_start.year, month_start.month)
        rows_by_day = await self.repo.timesheet_days(user_id=user.id, start=month_start, end=end)
        national_holidays = await self.holidays.national_dates()
        tz = ZoneInfo(account.timezone)

        days: list[TimesheetDay] = []
        cursor = month_start
        while cursor <= end:
            row = rows_by_day.get(cursor)
            first_access = row.first_access if row is not None else None
            last_access = row.last_access if row is not None else None
            access_count = row.access_count if row is not None else 0

            # Regra 6: sem jornada cadastrada, sem comparação — nunca desvio zero.
            deviation: int | None = None
            if first_access is not None and user.work_start is not None:
                deviation = _deviation_minutes(first_access.astimezone(tz).time(), user.work_start)

            days.append(
                TimesheetDay(
                    day=cursor,
                    first_access=first_access,
                    last_access=last_access,
                    access_count=access_count,
                    deviation_minutes=deviation,
                    is_weekend=cursor.weekday() >= 5,
                    is_holiday=cursor in national_holidays,
                )
            )
            cursor = cursor + timedelta(days=1)
        return days
