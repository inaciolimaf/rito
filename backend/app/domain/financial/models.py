from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, SmallInteger, func, text
from sqlalchemy.dialects.postgresql import ENUM as PGENUM
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin


class EntryType(StrEnum):
    """Natureza do lançamento financeiro (spec 054 §4) — RECEITA ou DESPESA."""

    RECEITA = "RECEITA"
    DESPESA = "DESPESA"


class DreGroup(Base):
    """Grupo do DRE (spec 054, regra 1) — taxonomia global e imutável, 10 grupos fixos
    para todo escritório (mesmo padrão de `Step`, spec 015: sem tenant_id, sem CRUD)."""

    __tablename__ = "dre_groups"

    id: Mapped[int] = mapped_column(  # type: ignore[assignment]
        SmallInteger(), primary_key=True, autoincrement=False
    )
    name: Mapped[str] = mapped_column(unique=True)
    nature: Mapped[EntryType] = mapped_column(
        PGENUM(EntryType, name="entry_type", create_type=False)
    )


class FinancialCategory(TenantMixin, Base):
    """Categoria financeira (spec 054) — classifica lançamentos (spec 056) por grupo
    DRE. `type` é independente da natureza do grupo (regra 2): duas categorias
    semeadas do ADVBOX real são RECEITA num grupo de natureza DESPESA — a validação
    de negócio é só sobre `dre_group_id` existir, nunca sobre bater com `type`."""

    __tablename__ = "financial_categories"

    dre_group_id: Mapped[int] = mapped_column(SmallInteger(), ForeignKey("dre_groups.id"))
    name: Mapped[str]
    type: Mapped[EntryType] = mapped_column(PGENUM(EntryType, name="entry_type", create_type=False))
    is_default: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class CostCenter(TenantMixin, Base):
    """Centro de custo (spec 054) — classificação livre de lançamentos por área/projeto.
    `is_default` marca o centro `GERAL` semeado (regra 8: nunca excluível) — não está no
    esboço SQL da spec, adicionado por necessidade (ver Descobertas)."""

    __tablename__ = "cost_centers"

    name: Mapped[str]
    is_default: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
