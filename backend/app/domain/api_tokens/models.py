"""Token de API e log de requisição (spec 095 §4)."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, SmallInteger, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, INET
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin


class ApiToken(TenantMixin, Base):
    """Um token de integração.

    O token em si NUNCA é guardado (regra 1): só o hash e os oito primeiros caracteres.
    O prefixo existe porque a pergunta operacional é "qual token está fazendo isso?", e
    um UUID interno não é algo que o integrador reconheça do lado dele.
    """

    __tablename__ = "api_tokens"

    name: Mapped[str]
    token_hash: Mapped[str] = mapped_column(unique=True)
    prefix: Mapped[str]
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text()), default=list, server_default=text("'{}'::text[]")
    )
    allowed_ips: Mapped[list[str] | None] = mapped_column(ARRAY(INET()), default=None)
    last_used_at: Mapped[datetime | None] = mapped_column(default=None)
    expires_at: Mapped[datetime | None] = mapped_column(default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(default=None)
    created_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ApiRequest(TenantMixin, Base):
    """Uma requisição da API pública (regra 9).

    É o que responde "por que meu script parou de funcionar às 3h da manhã?" — e a
    resposta precisa existir dias depois, não só enquanto o log estiver quente.
    """

    __tablename__ = "api_requests"

    token_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("api_tokens.id", ondelete="SET NULL"), default=None
    )
    method: Mapped[str]
    path: Mapped[str]
    status_code: Mapped[int] = mapped_column(SmallInteger())
    duration_ms: Mapped[int | None] = mapped_column(default=None)
    ip_address: Mapped[str | None] = mapped_column(INET(), default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
