"""Montagem do PostDetail (spec 040, alvo 2) — o "formato de saída" de um post com o
nome do tipo e as linhas de responsáveis. Separado de service.py para ser usado pelos
três consumidores (PostService, CreatePostUseCase, CompletePostUseCase) sem que um
importe o outro."""

from collections.abc import Sequence
from dataclasses import dataclass

from app.core.invariants import not_none
from app.domain.posts.models import Post, PostUser
from app.domain.posts.repository import PostRepository
from app.domain.task_types.repository import TaskTypeRepository
from app.domain.users.models import User


@dataclass
class AssigneeDetail:
    user: User
    line: PostUser


@dataclass
class PostDetail:
    post: Post
    task_type_name: str
    assignees: Sequence[AssigneeDetail]
    # Regra 8 (spec 033): tarefa privada para não envolvido — presença sem conteúdo.
    redacted: bool = False


async def build_detail(
    post: Post, *, posts: PostRepository, task_types: TaskTypeRepository
) -> PostDetail:
    """O detalhe completo de um post: nome do tipo + responsáveis com suas linhas."""
    task_type = await task_types.get_by_id(post.task_type_id)
    task_type = not_none(task_type, "a tarefa referencia um tipo existente (FK)")
    lines = await posts.assignee_lines_for([post.id])
    return PostDetail(
        post=post,
        task_type_name=task_type.name,
        assignees=[AssigneeDetail(user=user, line=line) for user, line in lines.get(post.id, [])],
    )
