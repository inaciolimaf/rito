"""Visibilidade da tarefa (spec 033, regra 8) — extraída do service quando a spec 035
precisou da mesma regra em anexos e comentários (regra dos 3 usos)."""

import uuid

from app.domain.posts.models import Post


def is_involved(post: Post, assignee_ids: set[uuid.UUID], user_id: uuid.UUID) -> bool:
    """Tarefa privada só é visível ao criador e aos responsáveis."""
    return post.created_by == user_id or user_id in assignee_ids
