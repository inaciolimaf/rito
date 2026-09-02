import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import CRIADO_EM, Base, TenantMixin


class ActionGroup(TenantMixin, Base):
    """Grupo de ação — spec 014. Área do direito; também define quem recebe as
    intimações do grupo (`publications_user_id`, usado pela 045)."""

    __tablename__ = "action_groups"

    name: Mapped[str]
    publications_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), default=None
    )
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)


class LawsuitType(TenantMixin, Base):
    """Tipo de ação — sempre pertence a um grupo (regra 2, spec 014)."""

    __tablename__ = "lawsuit_types"

    action_group_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("action_groups.id")
    )
    name: Mapped[str]
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)
