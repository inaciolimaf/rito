import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    # Toda coluna `Mapped[datetime]` vira TIMESTAMPTZ — sem isso o SQLAlchemy infere
    # DateTime "naive" por padrão, e o asyncpg rejeita datetime com tzinfo contra uma
    # coluna que ele acha que não tem timezone.
    type_annotation_map = {datetime: DateTime(timezone=True)}

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )


# O relógio dos carimbos de tempo (dívida 31).
#
# `now()` do Postgres devolve o instante de INÍCIO DA TRANSAÇÃO, não o do statement. Como a
# spec 105 passou a rodar cada teste dentro de uma transação única, todas as linhas criadas
# num mesmo teste nasciam com `created_at` IDÊNTICO — por mais requisições HTTP separadas que
# as tivessem criado. Com o valor de ordenação empatado, `paginate_keyset` desempatava por
# UUID v4, e um teste de ordenação virava cara ou coroa: `test_ordenacao_por_created_at_desc`
# falhava em ~metade das execuções, no HEAD limpo.
#
# `statement_timestamp()` é o instante do STATEMENT. Duas linhas inseridas por comandos
# diferentes recebem valores diferentes, dentro ou fora da mesma transação — medido nesta
# spec contra o banco real. Em produção a diferença é invisível (ninguém observa dois
# `INSERT` da mesma transação com precisão de microssegundo); em teste, é o que separa uma
# afirmação de um sorteio.
CRIADO_EM = func.statement_timestamp()


class TenantMixin:
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )


class Tenant(Base):
    __tablename__ = "tenants"

    slug: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)
    updated_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM, onupdate=CRIADO_EM)
