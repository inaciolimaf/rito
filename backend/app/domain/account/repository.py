from sqlalchemy import select

from app.core.repository import BaseRepository
from app.domain.account.models import Account


class AccountRepository(BaseRepository[Account]):
    model = Account

    async def get_current(self) -> Account | None:
        """1:1 por tenant — RLS já restringe a no máximo 1 linha visível."""
        result = await self.session.scalars(select(Account))
        return result.first()

    async def timezone(self) -> str | None:
        """Fuso do escritório, ou `None` quando a conta ainda não existe (spec 114).

        Regra 7: era o mesmo `get_current().timezone` escrito em dois lugares, com dois
        fallbacks diferentes. Aqui ele existe uma vez. Devolve `None` em vez do padrão
        de propósito — quem decide o fallback é o `Clock`, que já sabe fazer isso, e
        assim o padrão não volta a ser escrito à mão em cada chamador.

        Custa uma query, então NÃO serve para rota autenticada de `/api/v1`: lá o fuso
        vem de carona no `get_current_user` e o orçamento do §11 não tem folga. Isto é
        para quem não tem requisição (worker) ou não tem usuário logado (API pública).
        """
        account = await self.get_current()
        return account.timezone if account else None
