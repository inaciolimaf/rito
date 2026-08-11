import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.transfer import validated_transfer
from app.domain.financial.exceptions import (
    CostCenterNameAlreadyExistsError,
    DefaultCategoryNotDeletableError,
    DefaultCostCenterNotDeletableError,
    DreGroupNotFoundError,
    FinancialCategoryNameAlreadyExistsError,
)
from app.domain.financial.models import CostCenter, DreGroup, EntryType, FinancialCategory
from app.domain.financial.repository import (
    CostCenterRepository,
    DreGroupRepository,
    FinancialCategoryRepository,
)
from app.domain.financial.schemas import (
    CostCenterCreateRequest,
    CostCenterUpdateRequest,
    FinancialCategoryCreateRequest,
    FinancialCategoryUpdateRequest,
)


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
