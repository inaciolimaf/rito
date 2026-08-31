import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.transfer import validated_transfer
from app.domain.customer_origins.exceptions import (
    CustomerOriginInUseError,
    CustomerOriginNameAlreadyExistsError,
)
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
        # Regra 3 da 101: origem com contato vinculado exige transferência antes.
        if await self.origins.usage_count(origin.id) > 0:
            raise CustomerOriginInUseError
        await self.origins.delete(origin)

    async def transfer(self, *, from_id: uuid.UUID, to_id: uuid.UUID) -> int:
        # Regra 4 da 101: reatribui os contatos de verdade e devolve a contagem real
        # (fecha a dívida nº 13).
        async def reassign() -> int:
            return await self.origins.reassign(from_id=from_id, to_id=to_id)

        return await validated_transfer(
            from_id=from_id, to_id=to_id, get_by_id=self.origins.get_by_id, reassign=reassign
        )
