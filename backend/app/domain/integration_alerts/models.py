import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base


class IntegrationAlert(Base):
    """Alerta de integração externa (spec 046 §4) — DataJud, DJEN. `tenant_id` nulo
    é alerta de SISTEMA (ex.: `DATAJUD_API_KEY` é config global, não por tenant —
    regra 3): a política de RLS da migration 046 libera essas linhas para todo
    mundo, diferente do isolamento estrito de `TenantMixin`."""

    __tablename__ = "integration_alerts"

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), default=None
    )
    integration: Mapped[str] = mapped_column(Text)  # 'datajud' | 'djen'
    severity: Mapped[str] = mapped_column(Text)  # 'warning' | 'critical'
    code: Mapped[str] = mapped_column(Text)  # 'api_key_rotated' | ...
    message: Mapped[str] = mapped_column(Text)
    # Spec 049: a quem o alerta foi atribuído (responsável do termo, ou GESTOR de fallback) —
    # informativo, não controla visibilidade (isso continua sendo tenant_id + RLS).
    responsible_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), default=None
    )
    resolved_at: Mapped[datetime | None] = mapped_column(default=None)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
