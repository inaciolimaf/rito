import uuid
from datetime import datetime

from pydantic import BaseModel

from app.domain.financial.models import EntryType


class DreGroupResponse(BaseModel):
    id: int
    name: str
    nature: EntryType


class FinancialCategoryCreateRequest(BaseModel):
    name: str
    type: EntryType
    dre_group_id: int


class FinancialCategoryUpdateRequest(BaseModel):
    name: str
    type: EntryType
    dre_group_id: int
    is_active: bool = True


class FinancialCategoryResponse(BaseModel):
    id: uuid.UUID
    name: str
    type: EntryType
    dre_group_id: int
    dre_group_name: str
    is_default: bool
    is_active: bool
    created_at: datetime


class FinancialCategoryListResponse(BaseModel):
    items: list[FinancialCategoryResponse]
    next_cursor: None = None
    total: int


class CostCenterCreateRequest(BaseModel):
    name: str


class CostCenterUpdateRequest(BaseModel):
    name: str
    is_active: bool = True


class CostCenterResponse(BaseModel):
    id: uuid.UUID
    name: str
    is_default: bool
    is_active: bool
    created_at: datetime


class CostCenterListResponse(BaseModel):
    items: list[CostCenterResponse]
    next_cursor: None = None
    total: int


class TransferFinancialCategoriesRequest(BaseModel):
    from_id: uuid.UUID
    to_id: uuid.UUID


class TransferCostCentersRequest(BaseModel):
    from_id: uuid.UUID
    to_id: uuid.UUID
