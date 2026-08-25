"""Acesso a dados do registry de agregados (spec 078) — tabelas globais, sem RLS;
a sessão de request (rito_app) lê direto."""

from collections.abc import Sequence
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.aggregates.models import AggregateRegistry


class AggregateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> Sequence[AggregateRegistry]:
        stmt = select(AggregateRegistry).order_by(AggregateRegistry.name)
        return (await self.session.scalars(stmt)).all()

    async def get(self, name: str) -> AggregateRegistry | None:
        # populate_existing: o refresh manual (router) atualiza a linha por outra
        # conexão (superusuário) — sem isso a identity map devolveria o estado
        # cacheado de antes do refresh na mesma request.
        stmt = (
            select(AggregateRegistry)
            .where(AggregateRegistry.name == name)
            .execution_options(populate_existing=True)
        )
        return cast(AggregateRegistry | None, await self.session.scalar(stmt))
