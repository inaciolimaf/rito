import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.transfer import validated_transfer
from app.domain.customers.repository import CustomerRepository
from app.domain.financial.exceptions import (
    BankAccountNameAlreadyExistsError,
    CostCenterNameAlreadyExistsError,
    DefaultAccountNeedsReplacementError,
    DefaultCategoryNotDeletableError,
    DefaultCostCenterNotDeletableError,
    DreGroupNotFoundError,
    FinancialCategoryNameAlreadyExistsError,
    InstitutionNotFoundError,
    PaidTransactionNotDeletableError,
    TransactionAccountNotFoundError,
    TransactionCategoryNotFoundError,
    TransactionCategoryTypeMismatchError,
    TransactionCostCenterNotFoundError,
    TransactionCustomerNotFoundError,
    TransactionLawsuitNotFoundError,
)
from app.domain.financial.models import (
    AccountKind,
    BankAccount,
    CostCenter,
    DreGroup,
    EntryType,
    FinancialCategory,
    FinancialInstitution,
    Transaction,
    TransactionKind,
)
from app.domain.financial.repository import (
    BankAccountRepository,
    CostCenterRepository,
    DreGroupRepository,
    FinancialCategoryRepository,
    FinancialInstitutionRepository,
    TransactionRepository,
    TransactionRow,
)
from app.domain.financial.schemas import (
    BankAccountCreateRequest,
    BankAccountUpdateRequest,
    CostCenterCreateRequest,
    CostCenterUpdateRequest,
    FinancialCategoryCreateRequest,
    FinancialCategoryUpdateRequest,
    TransactionCreateRequest,
    TransactionUpdateRequest,
)
from app.domain.lawsuits.repository import LawsuitRepository
from app.domain.users.models import User


class DreGroupService:
    def __init__(self, session: AsyncSession) -> None:
        self.groups = DreGroupRepository(session)

    async def list_groups(self) -> list[DreGroup]:
        return list(await self.groups.list_all())


class FinancialCategoryService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.categories = FinancialCategoryRepository(session)
        self.groups = DreGroupRepository(session)

    async def list_categories(
        self,
        *,
        type_: EntryType | None,
        dre_group_id: int | None,
        is_active: bool | None,
        query: str | None,
    ) -> list[tuple[FinancialCategory, str]]:
        items = await self.categories.list_filtered(
            type_=type_, dre_group_id=dre_group_id, is_active=is_active, query=query
        )
        return [(category, await self._group_name(category.dre_group_id)) for category in items]

    async def get(self, category_id: uuid.UUID) -> tuple[FinancialCategory, str] | None:
        category = await self.categories.get_by_id(category_id)
        if category is None:
            return None
        return category, await self._group_name(category.dre_group_id)

    async def create(
        self, payload: FinancialCategoryCreateRequest
    ) -> tuple[FinancialCategory, str]:
        group_name = await self._group_name(payload.dre_group_id)
        if await self.categories.get_by_name(payload.name) is not None:
            raise FinancialCategoryNameAlreadyExistsError
        category = FinancialCategory(
            tenant_id=self.tenant_id,
            dre_group_id=payload.dre_group_id,
            name=payload.name,
            type=payload.type,
        )
        created = await self.categories.create(category)
        return created, group_name

    async def update(
        self, category: FinancialCategory, payload: FinancialCategoryUpdateRequest
    ) -> tuple[FinancialCategory, str]:
        group_name = await self._group_name(payload.dre_group_id)
        if payload.name != category.name:
            existing = await self.categories.get_by_name(payload.name)
            if existing is not None and existing.id != category.id:
                raise FinancialCategoryNameAlreadyExistsError

        category.name = payload.name
        category.type = payload.type
        category.dre_group_id = payload.dre_group_id
        category.is_active = payload.is_active
        return category, group_name

    async def delete(self, category: FinancialCategory) -> None:
        # Regra 3: categoria semeada não sai do banco — só inativa (via PUT).
        if category.is_default:
            raise DefaultCategoryNotDeletableError
        await self.categories.delete(category)

    async def transfer(self, *, from_id: uuid.UUID, to_id: uuid.UUID) -> int:
        # Regra 4: "excluir categoria em uso exige transferência". A validação é real; a
        # reatribuição é um no-op documentado — nada referencia financial_categories
        # ainda (lançamentos chegam na spec 056), mesmo padrão de customer_origins (016)/
        # stages (015)/action_groups (014).
        async def reassign() -> int:
            return 0

        return await validated_transfer(
            from_id=from_id, to_id=to_id, get_by_id=self.categories.get_by_id, reassign=reassign
        )

    async def _group_name(self, dre_group_id: int) -> str:
        group = await self.groups.get_by_id(dre_group_id)
        if group is None:
            raise DreGroupNotFoundError
        return group.name


class CostCenterService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.cost_centers = CostCenterRepository(session)

    async def list_cost_centers(
        self, *, is_active: bool | None, query: str | None
    ) -> list[CostCenter]:
        return list(await self.cost_centers.list_filtered(is_active=is_active, query=query))

    async def get(self, cost_center_id: uuid.UUID) -> CostCenter | None:
        return await self.cost_centers.get_by_id(cost_center_id)

    async def create(self, payload: CostCenterCreateRequest) -> CostCenter:
        if await self.cost_centers.get_by_name(payload.name) is not None:
            raise CostCenterNameAlreadyExistsError
        cost_center = CostCenter(tenant_id=self.tenant_id, name=payload.name)
        return await self.cost_centers.create(cost_center)

    async def update(self, cost_center: CostCenter, payload: CostCenterUpdateRequest) -> CostCenter:
        if payload.name != cost_center.name:
            existing = await self.cost_centers.get_by_name(payload.name)
            if existing is not None and existing.id != cost_center.id:
                raise CostCenterNameAlreadyExistsError

        cost_center.name = payload.name
        cost_center.is_active = payload.is_active
        return cost_center

    async def delete(self, cost_center: CostCenter) -> None:
        # Regra 8: o centro GERAL (semeado) nunca é excluível — só inativa.
        if cost_center.is_default:
            raise DefaultCostCenterNotDeletableError
        await self.cost_centers.delete(cost_center)

    async def transfer(self, *, from_id: uuid.UUID, to_id: uuid.UUID) -> int:
        # Mesmo no-op documentado de FinancialCategoryService.transfer acima — nada
        # referencia cost_centers ainda (contas/lançamentos chegam nas specs 055/056).
        async def reassign() -> int:
            return 0

        return await validated_transfer(
            from_id=from_id,
            to_id=to_id,
            get_by_id=self.cost_centers.get_by_id,
            reassign=reassign,
        )


class FinancialInstitutionService:
    def __init__(self, session: AsyncSession) -> None:
        self.institutions = FinancialInstitutionRepository(session)

    async def list_institutions(self, *, query: str | None) -> list[FinancialInstitution]:
        return list(await self.institutions.list_filtered(query=query))


class BankAccountService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.accounts = BankAccountRepository(session)
        self.institutions = FinancialInstitutionRepository(session)

    async def list_accounts(
        self, *, kind: AccountKind | None, is_active: bool | None
    ) -> list[tuple[BankAccount, str | None]]:
        items = await self.accounts.list_filtered(kind=kind, is_active=is_active)
        return [
            (account, await self._institution_name(account.institution_id)) for account in items
        ]

    async def get(self, account_id: uuid.UUID) -> tuple[BankAccount, str | None] | None:
        account = await self.accounts.get_by_id(account_id)
        if account is None:
            return None
        return account, await self._institution_name(account.institution_id)

    async def create(self, payload: BankAccountCreateRequest) -> tuple[BankAccount, str | None]:
        institution_name = await self._institution_name(payload.institution_id)
        if await self.accounts.get_by_name(payload.name) is not None:
            raise BankAccountNameAlreadyExistsError

        if payload.is_default:
            # flush() explícito (mesmo motivo de `set_default`): sem ele, o INSERT da
            # nova conta e o UPDATE que desmarca a antiga podem sair na ordem errada
            # dentro do mesmo flush e violar `ux_accounts_default`.
            await self._unset_current_default()
            await self.session.flush()

        account = BankAccount(
            tenant_id=self.tenant_id,
            kind=payload.kind,
            name=payload.name,
            institution_id=payload.institution_id,
            agency=payload.agency,
            account_number=payload.account_number,
            cycle_day=payload.cycle_day,
            due_day=payload.due_day,
            initial_amount=payload.initial_amount,
            is_default=payload.is_default,
        )
        created = await self.accounts.create(account)
        return created, institution_name

    async def update(
        self, account: BankAccount, payload: BankAccountUpdateRequest
    ) -> tuple[BankAccount, str | None]:
        institution_name = await self._institution_name(payload.institution_id)
        if payload.name != account.name:
            existing = await self.accounts.get_by_name(payload.name)
            if existing is not None and existing.id != account.id:
                raise BankAccountNameAlreadyExistsError
        # Regra 7: inativar a conta padrão exige eleger outra antes (via set-default).
        if account.is_default and account.is_active and not payload.is_active:
            raise DefaultAccountNeedsReplacementError

        account.kind = payload.kind
        account.name = payload.name
        account.institution_id = payload.institution_id
        account.agency = payload.agency
        account.account_number = payload.account_number
        account.cycle_day = payload.cycle_day
        account.due_day = payload.due_day
        # Regra 9: imutável depois do 1º lançamento — sem lançamentos ainda (spec 056),
        # não há o que guardar; livre por enquanto (ver Descobertas).
        account.initial_amount = payload.initial_amount
        account.is_active = payload.is_active
        return account, institution_name

    async def set_default(self, account: BankAccount) -> BankAccount:
        """Regra 2: só uma padrão ativa — desmarca a anterior na mesma transação.

        `flush()` explícito entre as duas mudanças: sem ele, o SQLAlchemy pode emitir
        os 2 UPDATEs no mesmo `executemany` em qualquer ordem, e como o índice único
        parcial não é `DEFERRABLE`, setar a nova ANTES de desmarcar a antiga viola a
        constraint mesmo as duas terminando corretas (achado ao testar — spec 055,
        Descobertas)."""
        await self._unset_current_default(except_id=account.id)
        await self.session.flush()
        account.is_default = True
        return account

    async def delete(self, account: BankAccount) -> None:
        # Regra 6: "conta com lançamento não pode ser excluída" — sem lançamentos
        # ainda (spec 056), nada bloqueia a exclusão por enquanto (ver Descobertas).
        await self.accounts.delete(account)

    async def get_balance(self, account: BankAccount, *, at: date | None) -> Decimal:
        # Regras 3/4: saldo = initial_amount + entradas - saídas / fatura = soma do
        # ciclo — ambas dependem de lançamentos (spec 056). Por enquanto devolve só o
        # saldo inicial, mesmo pra CARTAO_CREDITO (ver Descobertas).
        return account.initial_amount

    async def _unset_current_default(self, *, except_id: uuid.UUID | None = None) -> None:
        current = await self.accounts.get_default()
        if current is not None and current.id != except_id:
            current.is_default = False

    async def _institution_name(self, institution_id: int | None) -> str | None:
        if institution_id is None:
            return None
        institution = await self.institutions.get_by_id(institution_id)
        if institution is None:
            raise InstitutionNotFoundError
        return institution.name


class TransactionService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.transactions = TransactionRepository(session)
        self.categories = FinancialCategoryRepository(session)
        self.cost_centers = CostCenterRepository(session)
        self.accounts = BankAccountRepository(session)
        self.customers = CustomerRepository(session)
        self.lawsuits = LawsuitRepository(session)

    async def list_transactions(
        self,
        *,
        kind: TransactionKind | None,
        customer_id: uuid.UUID | None,
        lawsuit_id: uuid.UUID | None,
        status: str | None,
        due_from: date | None,
        due_to: date | None,
        q: str | None,
    ) -> list[TransactionRow]:
        return list(
            await self.transactions.list_filtered(
                kind=kind,
                customer_id=customer_id,
                lawsuit_id=lawsuit_id,
                status=status,
                due_from=due_from,
                due_to=due_to,
                q=q,
            )
        )

    async def get(self, transaction_id: uuid.UUID) -> TransactionRow | None:
        return await self.transactions.get_by_id_detail(transaction_id)

    async def create(self, payload: TransactionCreateRequest, actor: User) -> TransactionRow:
        await self._validate_references(payload)
        transaction = Transaction(
            tenant_id=self.tenant_id,
            kind=payload.kind,
            user_id=payload.user_id or actor.id,
            debit_account_id=payload.debit_account_id,
            credit_account_id=payload.credit_account_id,
            category_id=payload.category_id,
            cost_center_id=payload.cost_center_id,
            customer_id=payload.customer_id,
            lawsuit_id=payload.lawsuit_id,
            description=self._normalize_description(payload.description),
            amount=payload.amount,
            due_date=payload.due_date,
            payment_date=payload.payment_date,
            competence=payload.competence or self._derive_competence(payload.due_date),
        )
        created = await self.transactions.create(transaction)
        detail = await self.transactions.get_by_id_detail(created.id)
        assert detail is not None  # acabou de criar — sempre existe
        return detail

    async def update(
        self, transaction: Transaction, payload: TransactionUpdateRequest, actor: User
    ) -> TransactionRow:
        await self._validate_references(payload)
        transaction.kind = payload.kind
        transaction.user_id = payload.user_id or actor.id
        transaction.debit_account_id = payload.debit_account_id
        transaction.credit_account_id = payload.credit_account_id
        transaction.category_id = payload.category_id
        transaction.cost_center_id = payload.cost_center_id
        transaction.customer_id = payload.customer_id
        transaction.lawsuit_id = payload.lawsuit_id
        transaction.description = self._normalize_description(payload.description)
        transaction.amount = payload.amount
        transaction.due_date = payload.due_date
        transaction.payment_date = payload.payment_date
        transaction.competence = payload.competence or self._derive_competence(payload.due_date)
        detail = await self.transactions.get_by_id_detail(transaction.id)
        assert detail is not None  # acabou de atualizar — sempre existe
        return detail

    async def delete(self, transaction: Transaction) -> None:
        # Regra 10: lançamento pago exige estornar antes.
        if transaction.payment_date is not None:
            raise PaidTransactionNotDeletableError
        await self.transactions.delete(transaction)

    async def pay(self, transaction: Transaction, payment_date: date) -> Transaction:
        transaction.payment_date = payment_date
        return transaction

    async def unpay(self, transaction: Transaction) -> Transaction:
        transaction.payment_date = None
        return transaction

    async def _validate_references(
        self, payload: TransactionCreateRequest | TransactionUpdateRequest
    ) -> None:
        # Regra 1: RECEITA só aceita categoria RECEITA; DESPESA só DESPESA — a regra
        # que mais quebra integração (spec 056, Objetivo). Transferência não tem
        # categoria (já garantido pelo `_TransactionMixin._validate_shape`).
        if payload.category_id is not None:
            category = await self.categories.get_by_id(payload.category_id)
            if category is None:
                raise TransactionCategoryNotFoundError
            expected = (
                EntryType.RECEITA if payload.kind is TransactionKind.RECEITA else EntryType.DESPESA
            )
            if payload.kind is not TransactionKind.TRANSFERENCIA and category.type != expected:
                raise TransactionCategoryTypeMismatchError(category.type)
        if payload.cost_center_id is not None and (
            await self.cost_centers.get_by_id(payload.cost_center_id) is None
        ):
            raise TransactionCostCenterNotFoundError
        for account_id in (payload.debit_account_id, payload.credit_account_id):
            if account_id is not None and await self.accounts.get_by_id(account_id) is None:
                raise TransactionAccountNotFoundError
        if payload.customer_id is not None and (
            await self.customers.get_by_id(payload.customer_id) is None
        ):
            raise TransactionCustomerNotFoundError
        if payload.lawsuit_id is not None and (
            await self.lawsuits.get_by_id(payload.lawsuit_id) is None
        ):
            raise TransactionLawsuitNotFoundError

    @staticmethod
    def _normalize_description(description: str | None) -> str | None:
        # Regra 4: maiúsculas na gravação (paridade ADVBOX).
        return description.upper() if description else description

    @staticmethod
    def _derive_competence(due_date: date) -> date:
        # Regra 5: 1º dia do mês de due_date quando não informada.
        return due_date.replace(day=1)
