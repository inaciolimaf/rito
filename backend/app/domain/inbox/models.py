import uuid

from sqlalchemy import ForeignKey, SmallInteger, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY as PGARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin


class InboxPreference(TenantMixin, Base):
    """Ordem das seções e colapsos da caixa de entrada por usuário (spec 036).

    PK surrogate `id` (padrão Base de todo o projeto, mesma decisão da 013/032) +
    UNIQUE(user_id) com o mesmo efeito da PK (user_id) da spec: uma linha por usuário.
    """

    __tablename__ = "inbox_preferences"
    __table_args__ = (UniqueConstraint("user_id", name="uq_inbox_preferences_user"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    section_order: Mapped[list[str]] = mapped_column(
        PGARRAY(Text()),
        server_default=text(
            "ARRAY['deadline','publications','unread','urgent','important','others']"
        ),
    )
    collapsed_sections: Mapped[list[str]] = mapped_column(
        PGARRAY(Text()), default=list, server_default=text("'{}'")
    )
    page_size: Mapped[int] = mapped_column(SmallInteger(), default=100, server_default=text("100"))
