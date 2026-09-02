import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import CRIADO_EM, Base, TenantMixin


class Squad(TenantMixin, Base):
    """Time (squad) — spec 013. Agrupa colaboradores para atribuição futura de tarefas
    (032, fora de escopo aqui)."""

    __tablename__ = "squads"
    # A unicidade de nome é um ÍNDICE FUNCIONAL sobre immutable_unaccent(lower(name))
    # (migration 102, dívida nº 11) — expressão não é declarável em __table_args__,
    # igual às outras quatro taxonomias (014/015/016). Por isso não há
    # UniqueConstraint aqui: a regra vive no banco, não no modelo.

    name: Mapped[str]
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)
    updated_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM, onupdate=CRIADO_EM)


class SquadMember(TenantMixin, Base):
    """Associação time <-> usuário. PK é um `id` UUID surrogate + UNIQUE(squad_id,
    user_id) — a spec declara PK composta, mas `Base` (toda tabela do projeto) assume PK
    `id` única; efeito de unicidade é o mesmo (spec 013, Descobertas)."""

    __tablename__ = "squad_members"
    __table_args__ = (UniqueConstraint("squad_id", "user_id", name="uq_squad_members_squad_user"),)

    squad_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("squads.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
