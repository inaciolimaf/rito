import uuid
from datetime import datetime

from pydantic import BaseModel


class ActionGroupCreateRequest(BaseModel):
    name: str
    publications_user_id: uuid.UUID | None = None


class ActionGroupUpdateRequest(BaseModel):
    name: str
    publications_user_id: uuid.UUID | None = None
    is_active: bool = True


class ActionGroupResponse(BaseModel):
    id: uuid.UUID
    name: str
    publications_user_id: uuid.UUID | None
    is_active: bool
    lawsuit_types_count: int
    created_at: datetime


class ActionGroupListResponse(BaseModel):
    items: list[ActionGroupResponse]
    next_cursor: None = None
    total: int


class LawsuitTypeCreateRequest(BaseModel):
    name: str
    action_group_id: uuid.UUID


class LawsuitTypeUpdateRequest(BaseModel):
    name: str
    action_group_id: uuid.UUID
    is_active: bool = True


class LawsuitTypeResponse(BaseModel):
    id: uuid.UUID
    name: str
    action_group_id: uuid.UUID
    action_group_name: str
    is_active: bool
    created_at: datetime


class LawsuitTypeListResponse(BaseModel):
    items: list[LawsuitTypeResponse]
    next_cursor: None = None
    total: int


class TransferLawsuitTypesRequest(BaseModel):
    """`from_id`/`to_id` são ids de `action_groups` (spec 014, Descobertas: o
    "registro" que migra, regra 3, é o `lawsuit_type` — o endpoint reatribui todos os
    tipos do grupo de origem para o de destino, esvaziando o de origem para exclusão)."""

    from_id: uuid.UUID
    to_id: uuid.UUID
