import uuid
from datetime import date, datetime, time

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ENUM as PGENUM
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.dates import RecurrencePeriod, RecurrenceWeek
from app.core.models import Base, TenantMixin

# Os enums de recorrência moram em app/core/dates.py desde a spec 040 (alvo 1) — aqui
# ficam re-exportados: schemas/services/testes continuam importando de posts.models e
# os valores persistidos no PG enum (recurrence_period/recurrence_week) não mudaram.
__all__ = [
    "Post",
    "PostRecurrence",
    "PostUser",
    "RecurrencePeriod",
    "RecurrenceWeek",
]


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
    # Flags (spec 033): important e urgent são independentes e combináveis (regra 10);
    # is_future oculta até a data (regra 7); is_private restringe a visibilidade ao
    # criador e aos responsáveis — nem GESTOR vê (regra 8).
    is_important: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    is_urgent: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    is_future: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    is_private: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    show_in_schedule: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    # Spec 034: a ocorrência pertence a uma série de recorrência (NULL = tarefa avulsa).
    # SET NULL no delete da série — excluir a ocorrência/série não apaga o post.
    recurrence_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("post_recurrences.id", ondelete="SET NULL"),
        default=None,
    )
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
    # Conclusão é POR RESPONSÁVEL (spec 033, regra 1): cada linha fecha independente e
    # credita os pontos ali (regra 2 — points_earned = reward_snapshot do post, congelado).
    completed_at: Mapped[datetime | None] = mapped_column(default=None)
    points_earned: Mapped[int | None] = mapped_column(default=None)
    # Regra 9: ADMINISTRADOR pode concluir pela linha de outro — completed_by registra
    # quem executou (None = o próprio responsável concluiu).
    completed_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), default=None
    )
    # Regra 11: lida e estrela são por usuário, não da tarefa.
    is_read: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    is_starred: Mapped[bool] = mapped_column(default=False, server_default=text("false"))


class PostRecurrence(TenantMixin, Base):
    """Série de recorrência (spec 034): o post template é a PRIMEIRA ocorrência —
    as próximas são geradas ao concluir a atual (regra 1) ou pelo worker diário de
    segurança quando a data passa sem conclusão (regra 2). `occurrences_created`
    conta o template (nasce 1); `last_generated_date` ancora o cálculo da próxima
    data, então concluir uma ocorrência atrasada nunca volta a série no tempo."""

    __tablename__ = "post_recurrences"
    __table_args__ = (
        CheckConstraint(
            "max_occurrences IS NULL OR max_occurrences > 0",
            name="ck_post_recurrences_max_occurrences",
        ),
        UniqueConstraint("template_post_id", name="uq_post_recurrences_template"),
    )

    template_post_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE")
    )
    period: Mapped[RecurrencePeriod] = mapped_column(
        PGENUM(RecurrencePeriod, name="recurrence_period", create_type=False)
    )
    repeat_on: Mapped[RecurrenceWeek] = mapped_column(
        PGENUM(RecurrenceWeek, name="recurrence_week", create_type=False),
        default=RecurrenceWeek.DIA_EXATO,
        server_default=text("'DIA_EXATO'"),
    )
    # Regra 6: a série encerra pelo que vier primeiro — until_date ou max_occurrences.
    until_date: Mapped[date | None] = mapped_column(default=None)
    max_occurrences: Mapped[int | None] = mapped_column(default=None)
    occurrences_created: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    last_generated_date: Mapped[date | None] = mapped_column(default=None)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
