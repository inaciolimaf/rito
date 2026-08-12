import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    MetaData,
    Numeric,
    SmallInteger,
    Table,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PGENUM
from sqlalchemy.dialects.postgresql import UUID as PGUUID
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


class TransactionKind(StrEnum):
    """Os 3 tipos de lançamento (spec 056, regra 6) — o sinal vem do `kind`, `amount`
    é sempre positivo."""

    RECEITA = "RECEITA"
    DESPESA = "DESPESA"
    TRANSFERENCIA = "TRANSFERENCIA"


class Transaction(TenantMixin, Base):
    """Lançamento financeiro (spec 056) — receita, despesa ou transferência entre
    contas. `debit_account_id` é a conta do lançamento (RECEITA/DESPESA, opcional) ou
    a origem da transferência; `credit_account_id` só existe para transferência, o
    destino (regra 2 — as duas obrigatórias e diferentes só nesse caso)."""

    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_tx_amount_positive"),
        CheckConstraint(
            "kind <> 'TRANSFERENCIA' OR (credit_account_id IS NOT NULL "
            "AND debit_account_id IS NOT NULL AND debit_account_id <> credit_account_id)",
            name="ck_tx_transfer_accounts",
        ),
        CheckConstraint(
            "kind = 'TRANSFERENCIA' OR (category_id IS NOT NULL AND cost_center_id IS NOT NULL)",
            name="ck_tx_non_transfer_needs_category",
        ),
        CheckConstraint(
            "lawsuit_id IS NULL OR customer_id IS NOT NULL", name="ck_tx_lawsuit_needs_customer"
        ),
        CheckConstraint(
            "payment_date IS NULL OR payment_date <= CURRENT_DATE",
            name="ck_tx_payment_not_future",
        ),
    )

    kind: Mapped[TransactionKind] = mapped_column(
        PGENUM(TransactionKind, name="transaction_kind", create_type=False)
    )
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    debit_account_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("bank_accounts.id"), default=None
    )
    credit_account_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("bank_accounts.id"), default=None
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("financial_categories.id"), default=None
    )
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cost_centers.id"), default=None
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("customers.id"), default=None
    )
    lawsuit_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("lawsuits.id"), default=None
    )
    # Regra 4: convertida para maiúsculas na gravação (paridade ADVBOX) — feito no
    # service, não aqui (a coluna só guarda o que a aplicação já normalizou).
    description: Mapped[str | None] = mapped_column(default=None)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    due_date: Mapped[date]
    payment_date: Mapped[date | None] = mapped_column(default=None)
    # Regra 5: 1º dia do mês de `due_date` quando não informada — calculado no service.
    competence: Mapped[date]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    # Regra 057/1-9: preenchidos só quando o lançamento pertence a uma série (parcela
    # ou ocorrência de recorrência) — a maioria dos lançamentos continua avulsa.
    series_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("transaction_series.id"), default=None
    )
    installment_number: Mapped[int | None] = mapped_column(SmallInteger(), default=None)
    # Regra 1 (spec 058): lançamento de controle — nunca entra em saldo/fluxo de
    # caixa/DRE/DFC/inadimplência (excluído explicitamente onde esses cálculos existem,
    # ex.: TransactionRepository.lawsuit_financial_totals).
    is_internal: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    internal_note: Mapped[str | None] = mapped_column(default=None)


class FinancialRecurrence(StrEnum):
    """Os 5 períodos aceitos por lançamentos recorrentes (spec 057, regra 12) — mensal
    a anual; diária/semanal (que existem para tarefas, spec 034) não fazem sentido
    aqui. Mesmos nomes de `app.core.dates.RecurrencePeriod`, casa PG à parte."""

    MENSAL = "MENSAL"
    BIMESTRAL = "BIMESTRAL"
    TRIMESTRAL = "TRIMESTRAL"
    SEMESTRAL = "SEMESTRAL"
    ANUAL = "ANUAL"


class TransactionSeries(TenantMixin, Base):
    """Série de lançamentos (spec 057) — parcelamento (`is_installment=True`, todas as
    parcelas geradas na criação) ou recorrência (`is_installment=False`, gerada aos
    poucos por um worker que avança `generated_until`, regra 4)."""

    __tablename__ = "transaction_series"
    __table_args__ = (
        CheckConstraint(
            "is_installment = (total_installments IS NOT NULL)",
            name="ck_series_installment_has_count",
        ),
        CheckConstraint(
            "total_installments IS NULL OR total_installments BETWEEN 2 AND 100",
            name="ck_series_installment_range",
        ),
        CheckConstraint(
            "is_installment OR recurrence IS NOT NULL", name="ck_series_recurrence_needs_period"
        ),
    )

    is_installment: Mapped[bool]
    recurrence: Mapped[FinancialRecurrence | None] = mapped_column(
        PGENUM(FinancialRecurrence, name="financial_recurrence", create_type=False), default=None
    )
    total_installments: Mapped[int | None] = mapped_column(SmallInteger(), default=None)
    until_date: Mapped[date | None] = mapped_column(default=None)
    # Regra 4: a última data já gerada — o worker avança a partir daqui, nunca gera tudo
    # de uma vez para recorrência indefinida.
    generated_until: Mapped[date | None] = mapped_column(default=None)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


# View barreira sobre a materialized view account_daily_balances (migration 059) — o
# filtro de tenant está na definição da view, mesmo padrão de `user_monthly_scores`
# (taskscore/models.py). Tabela Core somente-leitura: nunca entra em create_all/migration.
account_daily_balances = Table(
    "account_daily_balances_visible",
    MetaData(),
    Column("tenant_id", PGUUID(as_uuid=True)),
    Column("account_id", PGUUID(as_uuid=True)),
    Column("day", Date),
    Column("balance_delta", Numeric(14, 2)),
)


@dataclass
class AccountDailyBalance:
    """Linha tipada da view barreira — o saldo real da conta é `initial_amount +
    balance_delta` (calculado no repositório, não na view — ver migration 059)."""

    account_id: uuid.UUID
    day: date
    balance_delta: Decimal
