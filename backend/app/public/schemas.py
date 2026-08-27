"""Formas da API pública (spec 095 §5).

Schemas próprios, e não os internos reaproveitados, por uma razão de contrato (regra 12):
os schemas internos mudam quando a UI muda, e a v1 pública não pode quebrar porque alguém
renomeou um campo numa tela. O custo é este arquivo; o benefício é que a mudança interna
não vaza para quem integrou.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PublicPage(BaseModel):
    items: list[Any]
    next_cursor: str | None = None
    total: int | None = None


class PublicCustomer(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    identification: str | None
    email: str | None
    cellphone: str | None
    phone: str | None
    city: str | None
    state: str | None
    origin_id: uuid.UUID | None
    birthdate: date | None
    is_archived: bool
    created_at: datetime


class PublicCustomerPage(PublicPage):
    items: list[PublicCustomer]


class PublicCustomerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2)
    origin_id: uuid.UUID
    type: str = "PF"
    identification: str | None = None
    email: str | None = None
    cellphone: str | None = None
    city: str | None = None
    state: str | None = None
    birthdate: date | None = None


class PublicLawsuit(BaseModel):
    id: uuid.UUID
    process_number: str | None
    protocol_number: str | None
    folder: str | None
    stage_id: uuid.UUID
    lawsuit_type_id: uuid.UUID
    responsible_id: uuid.UUID
    county: str | None
    case_value: Decimal | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class PublicLawsuitPage(PublicPage):
    items: list[PublicLawsuit]


class PublicLawsuitCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lawsuit_type_id: uuid.UUID
    stage_id: uuid.UUID
    user_id: uuid.UUID
    customer_id: uuid.UUID
    process_number: str | None = None
    folder: str | None = None
    county: str | None = None
    case_value: Decimal | None = None
    notes: str | None = None


class PublicLawsuitUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    folder: str | None = None
    county: str | None = None
    notes: str | None = None
    case_value: Decimal | None = None
    stage_id: uuid.UUID | None = None


class PublicMovement(BaseModel):
    id: uuid.UUID
    lawsuit_id: uuid.UUID
    origin: str
    occurred_at: datetime
    title: str
    body: str | None


class PublicMovementCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    occurred_at: datetime
    title: str = Field(min_length=1, max_length=500)
    body: str | None = None


class PublicStageChange(BaseModel):
    id: uuid.UUID
    from_stage_id: uuid.UUID | None
    to_stage_id: uuid.UUID
    changed_by: uuid.UUID | None
    changed_at: datetime


class PublicPost(BaseModel):
    id: uuid.UUID
    lawsuit_id: uuid.UUID
    task_type_id: uuid.UUID
    scheduled_date: date | None
    deadline_date: date | None
    comments: str | None
    is_important: bool
    is_urgent: bool
    created_at: datetime


class PublicPostPage(PublicPage):
    items: list[PublicPost]


class PublicPostCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lawsuit_id: uuid.UUID
    task_type_id: uuid.UUID
    user_ids: list[uuid.UUID] = Field(default_factory=list)
    scheduled_date: date | None = None
    deadline_date: date | None = None
    comments: str | None = None


class PublicPublication(BaseModel):
    id: uuid.UUID
    process_number: str | None
    court_code: str | None
    availability_date: date
    communication_type: str | None
    body: str | None
    is_active: bool


class PublicPublicationPage(PublicPage):
    items: list[PublicPublication]


class PublicTransaction(BaseModel):
    id: uuid.UUID
    kind: str
    amount: Decimal
    due_date: date
    payment_date: date | None
    competence: date
    description: str | None
    customer_id: uuid.UUID | None
    lawsuit_id: uuid.UUID | None
    category_id: uuid.UUID | None


class PublicTransactionPage(PublicPage):
    items: list[PublicTransaction]


class PublicTransactionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    amount: Decimal = Field(gt=0)
    due_date: date
    category_id: uuid.UUID
    cost_center_id: uuid.UUID
    debit_account_id: uuid.UUID | None = None
    credit_account_id: uuid.UUID | None = None
    description: str | None = None
    customer_id: uuid.UUID | None = None
    lawsuit_id: uuid.UUID | None = None


class PublicTransactionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    due_date: date | None = None
    payment_date: date | None = None


class PublicDocument(BaseModel):
    id: uuid.UUID
    scope_type: str
    scope_id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime


class PublicDocumentPage(PublicPage):
    items: list[PublicDocument]


class PublicReference(BaseModel):
    id: uuid.UUID | int
    name: str


class PublicSettings(BaseModel):
    """Os ids de referência da conta (spec 095 §5).

    Existe porque toda integração começa com a mesma dificuldade: criar um processo exige
    `stage_id`, `lawsuit_type_id` e `user_id`, e sem um endpoint que os liste o integrador
    teria que abrir o banco de dados de outra pessoa para descobrir.
    """

    tenant_id: uuid.UUID
    users: list[PublicReference]
    customer_origins: list[PublicReference]
    task_types: list[PublicReference]
    stages: list[PublicReference]
    lawsuit_types: list[PublicReference]
    financial_categories: list[PublicReference]
    cost_centers: list[PublicReference]
    bank_accounts: list[PublicReference]
