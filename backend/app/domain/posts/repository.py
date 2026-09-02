import uuid
from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy import Select, func, select, update
from sqlalchemy import delete as sql_delete

from app.core.repository import BaseRepository
from app.domain.posts.models import Post, PostRecurrence, PostUser
from app.domain.users.models import User


def _com_filtro_de_responsavel(
    stmt: Select[Any], *, assignee_id: uuid.UUID | None, only_open: bool
) -> Select[Any]:
    """Filtros que atravessam `post_users`.

    O `JOIN` só entra quando um deles é pedido, e traz o `distinct` junto: uma tarefa com
    três responsáveis apareceria três vezes sem ele. Filtro que não precisa do join não
    paga por ele.
    """
    if assignee_id is None and not only_open:
        return stmt
    stmt = stmt.join(PostUser, PostUser.post_id == Post.id)
    if assignee_id is not None:
        stmt = stmt.where(PostUser.user_id == assignee_id)
    if only_open:
        stmt = stmt.where(PostUser.completed_at.is_(None))
    return stmt.distinct()


class PostRepository(BaseRepository[Post]):
    model = Post

    async def create_with_assignees(self, post: Post, user_ids: Sequence[uuid.UUID]) -> Post:
        self.session.add(post)
        await self.session.flush()
        for user_id in dict.fromkeys(user_ids):  # dedupe preservando a ordem
            self.session.add(PostUser(tenant_id=post.tenant_id, post_id=post.id, user_id=user_id))
        await self.session.flush()
        return post

    async def replace_assignees(self, post: Post, user_ids: Sequence[uuid.UUID]) -> None:
        await self.session.execute(sql_delete(PostUser).where(PostUser.post_id == post.id))
        for user_id in dict.fromkeys(user_ids):
            self.session.add(PostUser(tenant_id=post.tenant_id, post_id=post.id, user_id=user_id))
        await self.session.flush()

    async def list_for_lawsuit(self, lawsuit_id: uuid.UUID) -> Sequence[Post]:
        stmt = (
            select(Post)
            .where(Post.lawsuit_id == lawsuit_id)
            .order_by(Post.scheduled_date.desc().nulls_last(), Post.created_at.desc())
        )
        return (await self.session.scalars(stmt)).all()

    async def search(
        self,
        *,
        date_from: date | None,
        date_to: date | None,
        by_deadline: bool,
        assignee_id: uuid.UUID | None,
        lawsuit_id: uuid.UUID | None,
        task_type_id: uuid.UUID | None,
        only_open: bool,
        limit: int,
    ) -> Sequence[Post]:
        """Busca de tarefas por filtros (spec 083 §5, `search_tasks`).

        Diferente da agenda (spec 037), que só enxerga o que tem `show_in_schedule`:
        aqui o recorte é a TAREFA, com ou sem compromisso marcado.
        """
        axis = Post.deadline_date if by_deadline else Post.scheduled_date
        stmt = select(Post).where(axis.is_not(None)).order_by(axis, Post.id).limit(limit)
        # Filtros diretos na própria tarefa — cada um é «se veio, restringe».
        diretos: tuple[tuple[Any, Any], ...] = (
            (date_from, axis >= date_from),
            (date_to, axis <= date_to),
            (lawsuit_id, Post.lawsuit_id == lawsuit_id),
            (task_type_id, Post.task_type_id == task_type_id),
        )
        for valor, condicao in diretos:
            if valor is not None:
                stmt = stmt.where(condicao)
        stmt = _com_filtro_de_responsavel(stmt, assignee_id=assignee_id, only_open=only_open)
        return (await self.session.scalars(stmt)).all()

    async def assignees_for(self, post_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[User]]:
        """Responsáveis de vários posts em UMA query (sem N+1), na ordem alfabética."""
        if not post_ids:
            return {}
        stmt = (
            select(PostUser.post_id, User)
            .join(User, User.id == PostUser.user_id)
            .where(PostUser.post_id.in_(post_ids))
            .order_by(User.name)
        )
        result: dict[uuid.UUID, list[User]] = {post_id: [] for post_id in post_ids}
        for post_id, user in await self.session.execute(stmt):
            result[post_id].append(user)
        return result

    async def assignee_lines_for(
        self, post_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[tuple[User, PostUser]]]:
        """Usuário + linha de conclusão (spec 033) de vários posts em UMA query."""
        if not post_ids:
            return {}
        stmt = (
            select(User, PostUser)
            .join(PostUser, PostUser.user_id == User.id)
            .where(PostUser.post_id.in_(post_ids))
            .order_by(User.name)
        )
        result: dict[uuid.UUID, list[tuple[User, PostUser]]] = {post_id: [] for post_id in post_ids}
        for user, line in await self.session.execute(stmt):
            result[line.post_id].append((user, line))
        return result

    async def assignee_ids_for(self, post_id: uuid.UUID) -> set[uuid.UUID]:
        stmt = select(PostUser.user_id).where(PostUser.post_id == post_id)
        return set((await self.session.scalars(stmt)).all())

    async def get_post_user(self, post_id: uuid.UUID, user_id: uuid.UUID) -> PostUser | None:
        """A linha de conclusão daquele responsável (spec 033, regra 1)."""
        stmt = select(PostUser).where(PostUser.post_id == post_id, PostUser.user_id == user_id)
        return (await self.session.scalars(stmt)).first()

    async def lines_for_post(self, post_id: uuid.UUID) -> Sequence[PostUser]:
        stmt = select(PostUser).where(PostUser.post_id == post_id)
        return (await self.session.scalars(stmt)).all()

    async def all_completed(self, post_id: uuid.UUID) -> bool:
        """A tarefa fechou como um todo (spec 033, regra 3): TODAS as linhas concluídas.
        Dado puro — mora aqui para o CompletePostUseCase e a conclusão em massa da
        caixa de entrada (spec 036) não duplicarem o loop."""
        lines = await self.lines_for_post(post_id)
        return all(item.completed_at is not None for item in lines)

    async def find_duplicates(
        self, *, lawsuit_id: uuid.UUID, task_type_id: uuid.UUID, scheduled_date: date | None
    ) -> Sequence[Post]:
        """Candidatos à duplicata da regra 4 — a comparação do CONJUNTO de
        responsáveis fica no service (volume por processo é baixo)."""
        stmt = select(Post).where(
            Post.lawsuit_id == lawsuit_id,
            Post.task_type_id == task_type_id,
        )
        if scheduled_date is None:
            stmt = stmt.where(Post.scheduled_date.is_(None))
        else:
            stmt = stmt.where(Post.scheduled_date == scheduled_date)
        return (await self.session.scalars(stmt)).all()

    async def count_for_task_type(self, task_type_id: uuid.UUID) -> int:
        """Uso de um tipo de tarefa (regra 5 da spec 031 — plugada aqui)."""
        stmt = select(func.count()).select_from(Post).where(Post.task_type_id == task_type_id)
        return int((await self.session.execute(stmt)).scalar_one())

    async def reassign_task_type(self, *, from_id: uuid.UUID, to_id: uuid.UUID) -> int:
        result = await self.session.execute(
            update(Post)
            .where(Post.task_type_id == from_id)
            .values(task_type_id=to_id)
            .execution_options(synchronize_session=False)
        )
        return int(result.rowcount)  # type: ignore[attr-defined]  # SQLAlchemy tipa `rowcount` só em `CursorResult`; um UPDATE/DELETE sempre devolve um.


class RecurrenceRepository(BaseRepository[PostRecurrence]):
    model = PostRecurrence

    async def get_for_post(self, post: Post) -> PostRecurrence | None:
        if post.recurrence_id is None:
            return None
        return await self.get_by_id(post.recurrence_id)

    async def series_date_exists(self, recurrence_id: uuid.UUID, day: date) -> bool:
        """Guarda de idempotência: a conclusão (regra 1) e o worker (regra 2) nunca
        geram duas ocorrências na mesma data."""
        stmt = (
            select(func.count())
            .select_from(Post)
            .where(Post.recurrence_id == recurrence_id, Post.scheduled_date == day)
        )
        return int((await self.session.execute(stmt)).scalar_one()) > 0

    async def list_overdue(self, today: date) -> Sequence[PostRecurrence]:
        """Séries ativas cuja última data gerada já passou — alvo do worker diário
        de segurança (regra 2)."""
        stmt = (
            select(PostRecurrence)
            .where(
                PostRecurrence.is_active.is_(True),
                PostRecurrence.last_generated_date < today,
            )
            .order_by(PostRecurrence.last_generated_date)
        )
        return (await self.session.scalars(stmt)).all()
