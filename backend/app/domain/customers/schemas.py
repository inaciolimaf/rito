import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator

from app.core.br_documents import (
    format_postal_code,
    is_valid_cpf_or_cnpj,
    is_valid_phone,
    is_valid_postal_code,
    strip_document_mask,
)
from app.domain.customers.models import PersonType


class MaritalStatusResponse(BaseModel):
    id: int
    name: str


class DuplicateCandidateResponse(BaseModel):
    id: uuid.UUID
    name: str


class CheckDuplicateResponse(BaseModel):
    """Regra 9: duplicata provável (mesmo nome + nascimento) — aviso não bloqueante."""

    has_duplicate: bool
    candidates: list[DuplicateCandidateResponse]


def _validate_identification(value: str | None) -> str | None:
    """Regras 1/2/3 (spec 018): CPF/CNPJ com DV real, banco guarda só dígitos."""
    if not value:
        return value
    if not is_valid_cpf_or_cnpj(value):
        raise ValueError("CPF/CNPJ inválido.")
    return strip_document_mask(value)


def _validate_phone(value: str | None) -> str | None:
    """Regra 4: 10 ou 11 dígitos, com DDD, sem DDI."""
    if not value:
        return value
    if not is_valid_phone(value):
        raise ValueError("Telefone inválido — use DDD, sem código de país.")
    return strip_document_mask(value)


def _validate_postal_code(value: str | None) -> str | None:
    """Regra 5: CEP normalizado para `99999-999`."""
    if not value:
        return value
    if not is_valid_postal_code(value):
        raise ValueError("CEP inválido — use 8 dígitos.")
    return format_postal_code(value)


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

    @field_validator("rep_identification")
    @classmethod
    def _check_rep_identification(cls, value: str | None) -> str | None:
        return _validate_identification(value)

    @field_validator("rep_postal_code")
    @classmethod
    def _check_rep_postal_code(cls, value: str | None) -> str | None:
        return _validate_postal_code(value)

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

    @field_validator("identification")
    @classmethod
    def _check_identification(cls, value: str | None) -> str | None:
        return _validate_identification(value)

    @field_validator("cellphone", "phone")
    @classmethod
    def _check_phone(cls, value: str | None) -> str | None:
        return _validate_phone(value)

    @field_validator("postal_code")
    @classmethod
    def _check_postal_code(cls, value: str | None) -> str | None:
        return _validate_postal_code(value)


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
