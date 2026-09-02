"""Histórico de busca (spec 096 §4)."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import CRIADO_EM, Base, TenantMixin


class SearchHistory(TenantMixin, Base):
    """O que a pessoa buscou e o que ela clicou.

    As duas informações juntas, e não só a consulta: saber que alguém buscou "Ana" e
    clicou no processo (e não no contato) é o que permite, depois, ordenar melhor — e é
    o que faz as buscas recentes serem úteis em vez de uma lista de tentativas.
    """

    __tablename__ = "search_history"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    query: Mapped[str]
    clicked_type: Mapped[str | None] = mapped_column(default=None)
    clicked_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)
