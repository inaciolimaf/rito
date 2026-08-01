import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import decode_cursor, encode_cursor
from app.domain.squads.exceptions import SquadNameAlreadyExistsError
from app.domain.squads.models import Squad
from app.domain.squads.repository import SquadRepository
from app.domain.squads.schemas import SquadCreateRequest, SquadUpdateRequest
from app.domain.users.models import User


class SquadService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.squads = SquadRepository(session)

    async def list_squads(
        self,
        *,
        is_active: bool | None,
        query: str | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[tuple[Squad, list[User]]], str | None, int]:
        decoded_cursor = decode_cursor(cursor) if cursor else None
        items, total = await self.squads.list_filtered(
            is_active=is_active, query=query, cursor=decoded_cursor, limit=limit
        )
        members_by_squad = await self.squads.get_members_for_squads([squad.id for squad in items])
        next_cursor = encode_cursor(items[-1].name, items[-1].id) if len(items) == limit else None
        result = [(squad, members_by_squad.get(squad.id, [])) for squad in items]
        return result, next_cursor, total

    async def get(self, squad_id: uuid.UUID) -> tuple[Squad, Sequence[User]] | None:
        squad = await self.squads.get_by_id(squad_id)
        if squad is None:
            return None
        members = await self.squads.get_members(squad_id)
        return squad, members

    async def create(self, payload: SquadCreateRequest) -> tuple[Squad, Sequence[User]]:
        # Regra 1: nome único por tenant -> 409.
        if await self.squads.get_by_name(payload.name) is not None:
            raise SquadNameAlreadyExistsError

        squad = Squad(tenant_id=self.tenant_id, name=payload.name)
        await self.squads.create(squad)
        if payload.member_ids:
            await self.squads.reconcile_members(
                squad_id=squad.id, tenant_id=self.tenant_id, member_ids=payload.member_ids
            )
        members = await self.squads.get_members(squad.id)
        return squad, members

    async def update(
        self, squad: Squad, payload: SquadUpdateRequest
    ) -> tuple[Squad, Sequence[User]]:
        if payload.name != squad.name:
            existing = await self.squads.get_by_name(payload.name)
            if existing is not None and existing.id != squad.id:
                raise SquadNameAlreadyExistsError

        squad.name = payload.name
        squad.is_active = payload.is_active
        # Regra 6: reconcilia — adiciona os novos, remove os ausentes (não é patch).
        await self.squads.reconcile_members(
            squad_id=squad.id, tenant_id=self.tenant_id, member_ids=payload.member_ids
        )
        # O SELECT dentro de reconcile_members dispara autoflush do UPDATE pendente
        # acima — como `updated_at` é onupdate=func.now() (valor só existe depois que o
        # Postgres computa), o SQLAlchemy marca o atributo como expirado (precisa
        # recarregar). Sem este refresh, o primeiro acesso síncrono a squad.updated_at
        # (na serialização da resposta) tenta recarregar via I/O fora de um contexto
        # async válido e quebra com MissingGreenlet.
        await self.session.refresh(squad)
        members = await self.squads.get_members(squad.id)
        return squad, members

    async def delete(self, squad: Squad) -> None:
        # Regra 5: excluir time não afeta tarefas já criadas a partir dele — não há FK de
        # squad_id em nenhuma outra tabela ainda (atribuição de tarefa a time é a 032,
        # fora de escopo), então o CASCADE de squad_members é a única limpeza necessária.
        await self.squads.delete(squad)
