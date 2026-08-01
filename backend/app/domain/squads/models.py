import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin


class Squad(TenantMixin, Base):
    """Time (squad) — spec 013. Agrupa colaboradores para atribuição futura de tarefas
    (032, fora de escopo aqui)."""

    __tablename__ = "squads"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_squads_tenant_name"),)

    name: Mapped[str]
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


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
