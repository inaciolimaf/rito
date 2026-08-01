from sqlalchemy import CHAR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class LocationBase(DeclarativeBase):
    """Base própria (não `app.core.models.Base`) — states/cities são taxonomias globais,
    sem tenant_id/RLS, com chave primária natural (`code`/`ibge_code`, dados reais do IBGE)
    em vez do `id` UUID surrogate que toda tabela de domínio usa. Migrations são hand-written
    (alembic env.py: `target_metadata = None`), então não há autogenerate dependendo de
    metadata compartilhada com `app.core.models.Base`."""


class State(LocationBase):
    __tablename__ = "states"

    code: Mapped[str] = mapped_column(CHAR(2), primary_key=True)
    name: Mapped[str]
    ibge_code: Mapped[int] = mapped_column(unique=True)


class City(LocationBase):
    __tablename__ = "cities"

    ibge_code: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    state_code: Mapped[str] = mapped_column(CHAR(2))
