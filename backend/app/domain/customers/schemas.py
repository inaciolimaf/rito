import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, model_validator

from app.domain.customers.models import PersonType


class MaritalStatusResponse(BaseModel):
    id: int
    name: str


class _RepresentativeMixin(BaseModel):
    has_representative: bool = False
    rep_name: str | None = None
    rep_identification: str | None = None
    rep_document: str | None = None
    rep_birthdate: date | None = None
    rep_country: str | None = None
    rep_state: str | None = None
    rep_city: str | None = None
    rep_street: str | None = None
    rep_region: str | None = None
    rep_postal_code: str | None = None

    @model_validator(mode="after")
    def _validate_representative(self) -> "_RepresentativeMixin":
        """Regra 4: `has_representative=true` exige `rep_name` (mesma checagem do CHECK
        constraint no banco — aqui só para devolver 422 antes de ir ao banco)."""
        if self.has_representative and not self.rep_name:
            raise ValueError("rep_name é obrigatório quando um representante é adicionado.")
        return self


class CustomerCreateRequest(_RepresentativeMixin):
    type: PersonType = PersonType.PF
    name: str
    origin_id: uuid.UUID
    identification: str | None = None
    document: str | None = None
    notes: str | None = None
    birthdate: date | None = None
    marital_status_id: int | None = None
    occupation: str | None = None
    gender: Literal["F", "M"] | None = None
    nationality: str | None = None
    mother_name: str | None = None
    cellphone: str | None = None
    phone: str | None = None
    email: str | None = None
    country: str = "BRASIL"
    postal_code: str | None = None
    state: str | None = None
    city: str | None = None
    street: str | None = None
    region: str | None = None
    number_pis: str | None = None
    number_ctps: str | None = None
    number_cid: str | None = None


class CustomerUpdateRequest(CustomerCreateRequest):
    pass


class CustomerResponse(BaseModel):
    id: uuid.UUID
    type: PersonType
    name: str
    identification: str | None
    document: str | None
    origin_id: uuid.UUID
    notes: str | None
    birthdate: date | None
    marital_status_id: int | None
    occupation: str | None
    gender: str | None
    nationality: str | None
    mother_name: str | None
    cellphone: str | None
    phone: str | None
    email: str | None
    country: str
    postal_code: str | None
    state: str | None
    city: str | None
    street: str | None
    region: str | None
    number_pis: str | None
    number_ctps: str | None
    number_cid: str | None
    photo_url: str | None
    has_representative: bool
    rep_name: str | None
    rep_identification: str | None
    rep_document: str | None
    rep_birthdate: date | None
    rep_country: str | None
    rep_state: str | None
    rep_city: str | None
    rep_street: str | None
    rep_region: str | None
    rep_postal_code: str | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime
