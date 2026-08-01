import uuid
from collections.abc import Sequence

from sqlalchemy import func, select

from app.core.repository import BaseRepository, build_sorted_keyset_query
from app.domain.squads.models import Squad, SquadMember
from app.domain.users.models import User


class SquadRepository(BaseRepository[Squad]):
    model = Squad

    async def get_by_name(self, name: str) -> Squad | None:
        result = await self.session.scalars(select(Squad).where(Squad.name == name))
        return result.first()

    async def list_filtered(
        self,
        *,
        is_active: bool | None = None,
        query: str | None = None,
        cursor: tuple[str, uuid.UUID] | None = None,
        limit: int = 20,
    ) -> tuple[Sequence[Squad], int]:
        filters = []
        if is_active is not None:
            filters.append(Squad.is_active.is_(is_active))
        if query:
            filters.append(Squad.name.ilike(f"%{query}%"))

        count_stmt = select(func.count()).select_from(Squad)
        for condition in filters:
            count_stmt = count_stmt.where(condition)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = build_sorted_keyset_query(Squad, sort_column=Squad.name, cursor=cursor, limit=limit)
        for condition in filters:
            stmt = stmt.where(condition)
        items = (await self.session.scalars(stmt)).all()

        return items, total

    async def get_members(self, squad_id: uuid.UUID) -> Sequence[User]:
        result = await self.session.scalars(
            select(User)
            .join(SquadMember, SquadMember.user_id == User.id)
            .where(SquadMember.squad_id == squad_id)
            .order_by(User.name)
        )
        return result.all()

    async def get_members_for_squads(
        self, squad_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[User]]:
        """Uma query só para a página inteira (evita N+1 por squad)."""
        if not squad_ids:
            return {}
        rows = (
            await self.session.execute(
                select(SquadMember.squad_id, User)
                .join(User, User.id == SquadMember.user_id)
                .where(SquadMember.squad_id.in_(squad_ids))
                .order_by(User.name)
            )
        ).all()

        members_by_squad: dict[uuid.UUID, list[User]] = {squad_id: [] for squad_id in squad_ids}
        for squad_id, user in rows:
            members_by_squad[squad_id].append(user)
        return members_by_squad

    async def reconcile_members(
        self, *, squad_id: uuid.UUID, tenant_id: uuid.UUID, member_ids: list[uuid.UUID]
    ) -> None:
        """Regra 6: PUT com member_ids[] reconcilia — adiciona os novos, remove os
        ausentes. Nunca apaga o usuário nem as tarefas atribuídas a ele (regra 3), só a
        linha de associação."""
        current = await self.session.scalars(
            select(SquadMember).where(SquadMember.squad_id == squad_id)
        )
        current_by_user = {member.user_id: member for member in current}

        wanted = set(member_ids)
        for user_id, member in current_by_user.items():
            if user_id not in wanted:
                await self.session.delete(member)

        for user_id in wanted - current_by_user.keys():
            self.session.add(SquadMember(tenant_id=tenant_id, squad_id=squad_id, user_id=user_id))
