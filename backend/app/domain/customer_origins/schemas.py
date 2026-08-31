import uuid
from datetime import datetime

from pydantic import BaseModel


class CustomerOriginCreateRequest(BaseModel):
    name: str


class CustomerOriginUpdateRequest(BaseModel):
    name: str
    is_active: bool = True


class CustomerOriginResponse(BaseModel):
    id: uuid.UUID
    name: str
    is_active: bool
    created_at: datetime


class CustomerOriginListResponse(BaseModel):
    items: list[CustomerOriginResponse]
    next_cursor: None = None
    total: int


class TransferCustomerOriginsRequest(BaseModel):
    """`from_id`/`to_id` são ids de `customer_origins` (regra 2). A reatribuição é real
    desde a spec 101 (regra 4): move `customers.origin_id` e devolve a contagem em
    `transferred_count`."""

    from_id: uuid.UUID
    to_id: uuid.UUID
