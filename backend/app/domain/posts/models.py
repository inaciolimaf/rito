import uuid
from datetime import date, datetime, time

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin


class Post(TenantMixin, Base):
    """Post (spec 032) — a entidade central do sistema: tarefa, compromisso de agenda,
    intimação recebida e comentário são todos posts; o que muda é o tipo e os campos
    preenchidos. `reward_snapshot` congela a pontuação do catálogo na criação (regra 3)
    — mudar o catálogo depois não reescreve o histórico de produtividade."""

    __tablename__ = "posts"
    __table_args__ = (
        # Regra 6: término nunca antes do compromisso.
        CheckConstraint(
            "end_date IS NULL OR scheduled_date IS NULL OR end_date >= scheduled_date",
            name="ck_posts_end_after_scheduled",
        ),
        # Regra 5: hora de término exige data de término.
        CheckConstraint("end_time IS NULL OR end_date IS NOT NULL", name="ck_posts_end_time"),
    )

    lawsuit_id: Mapped[uuid.UUID] = mapped_column(
        # Regra 8: excluir o processo remove as tarefas (a FK garante no hard delete —
        # o delete da API é soft); excluir a tarefa nunca afeta o processo.
        PGUUID(as_uuid=True),
        ForeignKey("lawsuits.id", ondelete="CASCADE"),
    )
    task_type_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("task_types.id")
    )
    created_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    scheduled_date: Mapped[date | None] = mapped_column(default=None)
    scheduled_time: Mapped[time | None] = mapped_column(default=None)
    end_date: Mapped[date | None] = mapped_column(default=None)
    end_time: Mapped[time | None] = mapped_column(default=None)
    # Regra 7: prazo fatal é independente da data de compromisso — sem constraint entre
    # eles, pode ser anterior.
    deadline_date: Mapped[date | None] = mapped_column(default=None)
    all_day: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    location: Mapped[str | None] = mapped_column(default=None)
    comments: Mapped[str | None] = mapped_column(default=None)
    reward_snapshot: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class PostUser(TenantMixin, Base):
    """Responsável pelo post (spec 032) — N:M; a atribuição por time (squad) expande
    para os membros ativos na criação e o time NÃO fica vinculado (regra 2)."""

    __tablename__ = "post_users"
    # PK surrogate `id` (padrão Base de todo o projeto, mesma decisão da 013) +
    # UNIQUE(post_id, user_id) com o mesmo efeito da PK composta da spec.
    __table_args__ = (UniqueConstraint("post_id", "user_id", name="uq_post_users_post_user"),)

    post_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
