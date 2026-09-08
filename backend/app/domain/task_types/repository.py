import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, literal, select, update

from app.core.repository import BaseRepository
from app.domain.task_types.models import TaskType


def _last_assigned_query(task_type: Any) -> Select[Any]:
    """A "última atribuição" da regra 9 da spec 031: `MAX` da criação das tarefas deste
    tipo que têm responsável.

    **Por que `posts.created_at` e não uma data de `post_users`.** A atribuição é a linha
    de `post_users`, e ela não guarda instante nenhum — só conclusão e pontos. O único
    carimbo disponível é o do post, e ele serve porque toda tarefa nasce com ao menos um
    responsável (`resolve_assignees`, regra 1 da 032): criar e atribuir são o mesmo
    instante. O que essa escolha NÃO enxerga é a troca de responsável posterior
    (`replace_assignees`) — ver §9 da spec 125.

    **Por que o `JOIN` mesmo assim.** Ele não muda o resultado hoje; muda o que a consulta
    afirma. "Atribuído a alguém" fica escrito na consulta em vez de depender de uma
    invariante que vive em outro arquivo, e o dia em que uma tarefa puder existir sem dono
    a resposta continua certa sem ninguém se lembrar daqui.

    `task_type` é o que casa com `posts.task_type_id`: `TaskType.id` faz dela uma subquery
    correlacionada (uma linha por tipo, dentro da listagem, sem query por linha); um UUID
    faz dela a resposta para um tipo só.

    Import local pelo mesmo motivo de `usage_count`/`reassign`: `posts` (032) é uma spec
    DEPOIS desta e importa `TaskTypeRepository`.
    """
    from app.domain.posts.models import Post, PostUser

    return (
        select(func.max(Post.created_at))
        .select_from(Post)
        .join(PostUser, PostUser.post_id == Post.id)
        .where(Post.task_type_id == task_type)
    )


class TaskTypeRepository(BaseRepository[TaskType]):
    model = TaskType

    async def get_by_name(self, name: str) -> TaskType | None:
        """Regra 7: comparação sem acento e sem caso (immutable_unaccent da 014)."""
        result = await self.session.scalars(
            select(TaskType).where(
                func.immutable_unaccent(func.lower(TaskType.name))
                == func.immutable_unaccent(func.lower(literal(name)))
            )
        )
        return result.first()

    def _filtered_stmt(
        self,
        *,
        step_id: int | None,
        is_active: bool | None,
        query: str | None,
    ) -> Select[Any]:
        stmt = select(TaskType).order_by(func.lower(TaskType.name))
        if step_id is not None:
            stmt = stmt.where(TaskType.step_id == step_id)
        if is_active is not None:
            stmt = stmt.where(TaskType.is_active.is_(is_active))
        if query:
            pattern = func.concat("%", func.immutable_unaccent(func.lower(literal(query))), "%")
            stmt = stmt.where(func.immutable_unaccent(func.lower(TaskType.name)).ilike(pattern))
        return stmt

    async def list_filtered(
        self,
        *,
        step_id: int | None,
        is_active: bool | None,
        query: str | None,
    ) -> Sequence[TaskType]:
        """O catálogo filtrado, sem a derivada — quem só precisa do tipo (a sugestão de
        tipo em `publications/analysis.py`) não paga pela subquery."""
        stmt = self._filtered_stmt(step_id=step_id, is_active=is_active, query=query)
        return (await self.session.scalars(stmt)).all()

    async def list_with_last_assigned(
        self,
        *,
        step_id: int | None,
        is_active: bool | None,
        query: str | None,
    ) -> Sequence[tuple[TaskType, datetime | None]]:
        """O mesmo catálogo com a última atribuição de cada linha, em UMA query.

        A derivada entra como coluna correlacionada, não como consulta por item: com 152
        tipos por escritório, uma query por linha seria exatamente o N+1 que o orçamento
        do CLAUDE.md §11 existe para barrar (a listagem cabe em 3 statements, e dois deles
        já têm dono — o usuário do token e o catálogo de fases).
        """
        stmt = self._filtered_stmt(step_id=step_id, is_active=is_active, query=query).add_columns(
            _last_assigned_query(TaskType.id).correlate(TaskType).scalar_subquery()
        )
        return [(tipo, ultimo) for tipo, ultimo in await self.session.execute(stmt)]

    async def last_assigned_at(self, task_type_id: uuid.UUID) -> datetime | None:
        """A mesma derivada para um tipo só — o que as respostas de POST/PUT devolvem.

        Mesma consulta da listagem, sem correlação: uma fonte de verdade para o campo, e
        não uma na listagem e outra no detalhe (que foi como ele nasceu constante).
        """
        valor: datetime | None = (
            await self.session.execute(_last_assigned_query(task_type_id))
        ).scalar_one()
        return valor

    async def names_for(self, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        """Nomes de vários tipos em UMA query — a listagem de posts do processo (032)
        evita N+1 com ela."""
        if not ids:
            return {}
        stmt = select(TaskType.id, TaskType.name).where(TaskType.id.in_(ids))
        return {id_: str(name) for id_, name in await self.session.execute(stmt)}

    async def usage_count(self, task_type_id: uuid.UUID) -> int:
        """Quantas tarefas (posts) usam o tipo — plugado na tabela real na spec 032."""
        from app.domain.posts.models import Post

        stmt = select(func.count()).select_from(Post).where(Post.task_type_id == task_type_id)
        return int((await self.session.execute(stmt)).scalar_one())

    async def reassign(self, *, from_id: uuid.UUID, to_id: uuid.UUID) -> int:
        """Transferência em lote (regra 5 da 031) — UPDATE único nos posts."""
        from app.domain.posts.models import Post

        result = await self.session.execute(
            update(Post)
            .where(Post.task_type_id == from_id)
            .values(task_type_id=to_id)
            .execution_options(synchronize_session=False)
        )
        return int(result.rowcount)  # type: ignore[attr-defined]  # SQLAlchemy tipa `rowcount` só em `CursorResult`; um UPDATE/DELETE sempre devolve um.
