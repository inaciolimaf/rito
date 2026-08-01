import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.transfer import validated_transfer
from app.domain.customer_origins.exceptions import CustomerOriginNameAlreadyExistsError
from app.domain.customer_origins.models import CustomerOrigin
from app.domain.customer_origins.repository import CustomerOriginRepository
from app.domain.customer_origins.schemas import (
    CustomerOriginCreateRequest,
    CustomerOriginUpdateRequest,
)


class CustomerOriginService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.origins = CustomerOriginRepository(session)

    async def list_origins(
        self, *, is_active: bool | None, query: str | None
    ) -> list[CustomerOrigin]:
        return list(await self.origins.list_filtered(is_active=is_active, query=query))

    async def get(self, origin_id: uuid.UUID) -> CustomerOrigin | None:
        return await self.origins.get_by_id(origin_id)

    async def create(self, payload: CustomerOriginCreateRequest) -> CustomerOrigin:
        if await self.origins.get_by_name(payload.name) is not None:
            raise CustomerOriginNameAlreadyExistsError
        origin = CustomerOrigin(tenant_id=self.tenant_id, name=payload.name)
        return await self.origins.create(origin)

    async def update(
        self, origin: CustomerOrigin, payload: CustomerOriginUpdateRequest
    ) -> CustomerOrigin:
        if payload.name != origin.name:
            existing = await self.origins.get_by_name(payload.name)
            if existing is not None and existing.id != origin.id:
                raise CustomerOriginNameAlreadyExistsError

        origin.name = payload.name
        origin.is_active = payload.is_active
        return origin

    async def delete(self, origin: CustomerOrigin) -> None:
        # Nada referencia origin_id ainda (customers chega na spec 017) — sem guarda de
        # "em uso" por enquanto (spec 016, Descobertas).
        await self.origins.delete(origin)

    async def transfer(self, *, from_id: uuid.UUID, to_id: uuid.UUID) -> int:
        # Regra 2: "excluir origem em uso exige transferência". A validação é real; a
        # migração de dados continua um no-op — customers.origin_id existe desde a spec
        # 017, mas implementar a reatribuição real muda comportamento observável (deixa de
        # ser sempre 0), o que uma spec de refatoração não pode fazer (CLAUDE.md §8;
        # docs/DIVIDA-TECNICA.md #13).
        async def reassign() -> int:
            return 0

        return await validated_transfer(
            from_id=from_id, to_id=to_id, get_by_id=self.origins.get_by_id, reassign=reassign
        )
