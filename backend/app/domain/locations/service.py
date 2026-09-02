"""Taxonomia de estados e cidades (spec 118, checagem 2).

Módulo de leitura pura: as duas rotas não têm regra nenhuma além de "normaliza a UF e
lista". O service existe mesmo assim porque a camada é o contrato — o dia em que a
listagem ganhar cache, limite por tenant ou ordenação por uso, o lugar já está feito e
o router não muda. Sem `tenant_id`: `states`/`cities` é tabela global, sem RLS a
respeitar (ver o docstring do `StateRepository`).
"""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.locations.models import City, State
from app.domain.locations.repository import CityRepository, StateRepository


class LocationService:
    def __init__(self, session: AsyncSession) -> None:
        self.states = StateRepository(session)
        self.cities = CityRepository(session)

    async def list_states(self) -> Sequence[State]:
        return await self.states.list_all()

    async def list_cities(self, *, state_code: str, query: str | None) -> Sequence[City]:
        # A normalização da UF é regra, não HTTP: quem consulta `cities` por `sp` e por
        # `SP` tem de receber a mesma coisa, venha a chamada do router ou de um worker.
        return await self.cities.list_filtered(state_code=state_code.upper(), query=query)
