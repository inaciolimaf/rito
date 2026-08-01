from sqlalchemy import select

from app.core.repository import BaseRepository
from app.domain.account.models import Account


class AccountRepository(BaseRepository[Account]):
    model = Account

    async def get_current(self) -> Account | None:
        """1:1 por tenant — RLS já restringe a no máximo 1 linha visível."""
        result = await self.session.scalars(select(Account))
        return result.first()
