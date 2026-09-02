import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, text
from sqlalchemy.dialects.postgresql import ARRAY as PGARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import CRIADO_EM, Base, TenantMixin


class PostComment(TenantMixin, Base):
    """Comentário da thread da tarefa (spec 035). As menções são persistidas como
    ids em `mentioned_user_ids` (regra 1 — renomear o usuário não quebra o link);
    a exclusão é soft em `deleted_at` (regra 4 — a thread se preserva)."""

    __tablename__ = "post_comments"

    post_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE")
    )
    author_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    body: Mapped[str]
    mentioned_user_ids: Mapped[list[uuid.UUID]] = mapped_column(
        PGARRAY(PGUUID(as_uuid=True)), default=list, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)
    updated_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM, onupdate=CRIADO_EM)
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)
