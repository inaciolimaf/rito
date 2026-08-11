from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Numeric,
    SmallInteger,
    UniqueConstraint,
    func,
    text,
)
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


class AccountKind(StrEnum):
    """Os 5 tipos de conta (spec 055, regra 1) — só `CARTAO_CREDITO` usa ciclo/vencimento."""

    CORRENTE = "CORRENTE"
    POUPANCA = "POUPANCA"
    INVESTIMENTO = "INVESTIMENTO"
    CARTAO_CREDITO = "CARTAO_CREDITO"
    OUTRO = "OUTRO"


class FinancialInstitution(Base):
    """Instituição financeira (spec 055) — taxonomia global e imutável (mesmo padrão
    de `DreGroup`/`Step`). `id` é o próprio código COMPE do Banco Central."""

    __tablename__ = "financial_institutions"

    id: Mapped[int] = mapped_column(  # type: ignore[assignment]
        SmallInteger(), primary_key=True, autoincrement=False
    )
    name: Mapped[str] = mapped_column(unique=True)
    compe_code: Mapped[str | None] = mapped_column(default=None)


class BankAccount(TenantMixin, Base):
    """Conta bancária ou cartão de crédito (spec 055) — cartão é um `kind` desta mesma
    tabela, não uma entidade própria (regra 1: só ganha `cycle_day`/`due_day`)."""

    __tablename__ = "bank_accounts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_bank_accounts_tenant_name"),
        CheckConstraint(
            "kind <> 'CARTAO_CREDITO' OR (cycle_day BETWEEN 1 AND 31 AND due_day BETWEEN 1 AND 31)",
            name="ck_bank_accounts_card_needs_cycle",
        ),
        CheckConstraint(
            "kind = 'CARTAO_CREDITO' OR (cycle_day IS NULL AND due_day IS NULL)",
            name="ck_bank_accounts_non_card_no_cycle",
        ),
    )

    kind: Mapped[AccountKind] = mapped_column(
        PGENUM(AccountKind, name="account_kind", create_type=False)
    )
    name: Mapped[str]
    institution_id: Mapped[int | None] = mapped_column(
        SmallInteger(), ForeignKey("financial_institutions.id"), default=None
    )
    agency: Mapped[str | None] = mapped_column(default=None)
    account_number: Mapped[str | None] = mapped_column(default=None)
    # Só preenchido quando kind=CARTAO_CREDITO (regra 1, CHECK constraints acima).
    cycle_day: Mapped[int | None] = mapped_column(SmallInteger(), default=None)
    due_day: Mapped[int | None] = mapped_column(SmallInteger(), default=None)
    initial_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=0, server_default=text("0")
    )
    # Regra 2: 1 padrão ativa por tenant — garantido por índice único parcial na
    # migration (ux_accounts_default), não pela aplicação.
    is_default: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
