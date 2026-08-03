import uuid
from collections.abc import Sequence

from sqlalchemy import func, or_, select

from app.core.repository import BaseRepository, build_sorted_keyset_query
from app.domain.users.models import Occupation, User, UserInvitation, UserRole


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.scalars(select(User).where(User.email == email))
        return result.first()

    async def list_active_basic(self) -> Sequence[User]:
        """Usuários ativos do tenant (id + nome) — candidatos da resolução de @menções
        (spec 035, regra 1)."""
        stmt = select(User).where(User.is_active.is_(True)).order_by(User.name)
        return (await self.session.scalars(stmt)).all()

    async def names_for(self, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        """Nome de vários usuários em UMA query (sem N+1 nas listagens)."""
        if not user_ids:
            return {}
        stmt = select(User.id, User.name).where(User.id.in_(user_ids))
        return {user_id: name for user_id, name in await self.session.execute(stmt)}

    async def list_filtered(
        self,
        *,
        role: UserRole | None = None,
        is_active: bool | None = None,
        query: str | None = None,
        cursor: tuple[str, uuid.UUID] | None = None,
        limit: int = 20,
    ) -> tuple[Sequence[User], int]:
        """Listagem paginada (CLAUDE.md §6) — devolve `(itens, total)`, `total` sempre sem
        paginação (conta todas as linhas que passam nos filtros, não só a página)."""
        filters = []
        if role is not None:
            filters.append(User.role == role)
        if is_active is not None:
            filters.append(User.is_active.is_(is_active))
        if query:
            like_pattern = f"%{query}%"
            filters.append(or_(User.name.ilike(like_pattern), User.email.ilike(like_pattern)))

        count_stmt = select(func.count()).select_from(User)
        for condition in filters:
            count_stmt = count_stmt.where(condition)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = build_sorted_keyset_query(User, sort_column=User.name, cursor=cursor, limit=limit)
        for condition in filters:
            stmt = stmt.where(condition)
        items = (await self.session.scalars(stmt)).all()

        return items, total

    async def count_active_gestores(self, *, excluding: uuid.UUID | None = None) -> int:
        """Regra 8: não é possível inativar o último GESTOR ativo do tenant."""
        stmt = (
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.GESTOR, User.is_active.is_(True))
        )
        if excluding is not None:
            stmt = stmt.where(User.id != excluding)
        return (await self.session.execute(stmt)).scalar_one()


class UserInvitationRepository(BaseRepository[UserInvitation]):
    model = UserInvitation

    async def get_by_token_hash(self, token_hash: str) -> UserInvitation | None:
        result = await self.session.scalars(
            select(UserInvitation).where(UserInvitation.token_hash == token_hash)
        )
        return result.first()

    async def get_pending_by_email(self, email: str) -> UserInvitation | None:
        """Convite ainda não aceito para este e-mail — regra 1: reenviar invalida o
        anterior, então só pode haver um pendente por vez."""
        result = await self.session.scalars(
            select(UserInvitation).where(
                UserInvitation.email == email, UserInvitation.accepted_at.is_(None)
            )
        )
        return result.first()


class OccupationRepository(BaseRepository[Occupation]):
    model = Occupation

    async def list_all(self) -> Sequence[Occupation]:
        result = await self.session.scalars(select(Occupation).order_by(Occupation.name))
        return result.all()

    async def get_by_occupation_id(self, id_: int) -> Occupation | None:
        # BaseRepository.get_by_id espera uuid.UUID (toda outra tabela usa PK UUID) —
        # occupations é a única com PK inteira, daí um método com nome próprio em vez de
        # sobrescrever get_by_id com um tipo de parâmetro incompatível.
        return await self.session.get(Occupation, id_)
