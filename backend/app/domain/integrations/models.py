from datetime import datetime

from sqlalchemy import Boolean, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import CRIADO_EM, Base


class IntegrationHealth(Base):
    """Telemetria da checagem diária de saúde (spec 049, §4) — global do sistema,
    mesmo padrão de `CnjMovementCode` (spec 046): sem `tenant_id`, sem RLS. A saúde
    do DJEN/DataJud não é dado de nenhum tenant."""

    __tablename__ = "integration_health"

    integration: Mapped[str] = mapped_column(Text)  # 'djen' | 'datajud'
    checked_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)
    is_healthy: Mapped[bool] = mapped_column(Boolean)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[str | None] = mapped_column(Text)
