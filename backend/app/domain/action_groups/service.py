import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.action_groups.exceptions import (
    ActionGroupInUseError,
    ActionGroupNameAlreadyExistsError,
    ActionGroupNotFoundError,
    InvalidTransferError,
    LawsuitTypeNameAlreadyExistsError,
)
from app.domain.action_groups.models import ActionGroup, LawsuitType
from app.domain.action_groups.repository import ActionGroupRepository, LawsuitTypeRepository
from app.domain.action_groups.schemas import (
    ActionGroupCreateRequest,
    ActionGroupUpdateRequest,
    LawsuitTypeCreateRequest,
    LawsuitTypeUpdateRequest,
)


class ActionGroupService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.groups = ActionGroupRepository(session)

    async def list_groups(
        self, *, is_active: bool | None, query: str | None
    ) -> list[tuple[ActionGroup, int]]:
        items = await self.groups.list_filtered(is_active=is_active, query=query)
        counts = await self.groups.count_lawsuit_types([group.id for group in items])
        return [(group, counts.get(group.id, 0)) for group in items]

    async def get(self, group_id: uuid.UUID) -> tuple[ActionGroup, int] | None:
        group = await self.groups.get_by_id(group_id)
        if group is None:
            return None
        counts = await self.groups.count_lawsuit_types([group_id])
        return group, counts.get(group_id, 0)

    async def create(self, payload: ActionGroupCreateRequest) -> ActionGroup:
        if await self.groups.get_by_name(payload.name) is not None:
            raise ActionGroupNameAlreadyExistsError
        group = ActionGroup(
            tenant_id=self.tenant_id,
            name=payload.name,
            publications_user_id=payload.publications_user_id,
        )
        return await self.groups.create(group)

    async def update(self, group: ActionGroup, payload: ActionGroupUpdateRequest) -> ActionGroup:
        if payload.name != group.name:
            existing = await self.groups.get_by_name(payload.name)
            if existing is not None and existing.id != group.id:
                raise ActionGroupNameAlreadyExistsError

        group.name = payload.name
        group.publications_user_id = payload.publications_user_id
        group.is_active = payload.is_active
        return group

    async def delete(self, group: ActionGroup) -> None:
        # Regra 3: grupo com tipos vinculados exige transferência antes de excluir.
        counts = await self.groups.count_lawsuit_types([group.id])
        if counts.get(group.id, 0) > 0:
            raise ActionGroupInUseError
        await self.groups.delete(group)


class LawsuitTypeService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.types = LawsuitTypeRepository(session)
        self.groups = ActionGroupRepository(session)

    async def list_types(
        self,
        *,
        action_group_id: uuid.UUID | None,
        is_active: bool | None,
        query: str | None,
    ) -> list[tuple[LawsuitType, str]]:
        items = await self.types.list_filtered(
            action_group_id=action_group_id, is_active=is_active, query=query
        )
        return [(item, await self._group_name(item.action_group_id)) for item in items]

    async def get(self, type_id: uuid.UUID) -> tuple[LawsuitType, str] | None:
        lawsuit_type = await self.types.get_by_id(type_id)
        if lawsuit_type is None:
            return None
        return lawsuit_type, await self._group_name(lawsuit_type.action_group_id)

    async def create(self, payload: LawsuitTypeCreateRequest) -> tuple[LawsuitType, str]:
        if await self.types.get_by_name(payload.name) is not None:
            raise LawsuitTypeNameAlreadyExistsError
        group_name = await self._group_name(payload.action_group_id)

        lawsuit_type = LawsuitType(
            tenant_id=self.tenant_id, action_group_id=payload.action_group_id, name=payload.name
        )
        created = await self.types.create(lawsuit_type)
        return created, group_name

    async def update(
        self, lawsuit_type: LawsuitType, payload: LawsuitTypeUpdateRequest
    ) -> tuple[LawsuitType, str]:
        if payload.name != lawsuit_type.name:
            existing = await self.types.get_by_name(payload.name)
            if existing is not None and existing.id != lawsuit_type.id:
                raise LawsuitTypeNameAlreadyExistsError

        group_name = await self._group_name(payload.action_group_id)
        lawsuit_type.name = payload.name
        lawsuit_type.action_group_id = payload.action_group_id
        lawsuit_type.is_active = payload.is_active
        return lawsuit_type, group_name

    async def delete(self, lawsuit_type: LawsuitType) -> None:
        # Nada referencia lawsuit_types ainda (lawsuits/processos chega em spec futura) —
        # sem guarda de "em uso" por enquanto (spec 014, Descobertas).
        await self.types.delete(lawsuit_type)

    async def transfer(self, *, from_id: uuid.UUID, to_id: uuid.UUID) -> int:
        # Regra 3/7: "os registros migram para o destino" — os registros são os
        # lawsuit_types do grupo de origem, reatribuídos ao grupo de destino.
        if from_id == to_id:
            raise InvalidTransferError
        from_group = await self.groups.get_by_id(from_id)
        to_group = await self.groups.get_by_id(to_id)
        if from_group is None or to_group is None:
            raise InvalidTransferError
        return await self.types.reassign_group(from_group_id=from_id, to_group_id=to_id)

    async def _group_name(self, group_id: uuid.UUID) -> str:
        group = await self.groups.get_by_id(group_id)
        if group is None:
            raise ActionGroupNotFoundError
        return group.name
