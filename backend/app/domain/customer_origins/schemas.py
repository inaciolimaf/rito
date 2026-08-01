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
    """`from_id`/`to_id` são ids de `customer_origins` (regra 2). Nada referencia
    `origin_id` ainda (spec 016, Descobertas: `customers` só chega na spec 017), então a
    migração hoje não move nenhum dado real; o contrato fica pronto para quando houver o que
    mover."""

    from_id: uuid.UUID
    to_id: uuid.UUID
