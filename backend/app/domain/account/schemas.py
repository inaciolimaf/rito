import re
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator

from app.core.br_documents import is_valid_cpf_or_cnpj, strip_document_mask
from app.domain.account.models import DEFAULT_TIMEZONE, AccountPlan

# As 8 timezones do levantamento ADVBOX (spec 011, seção 4) — Brasil + Portugal.
ALLOWED_TIMEZONES = frozenset(
    {
        "America/Sao_Paulo",
        "America/Noronha",
        "America/Belem",
        "America/Manaus",
        "America/Rio_Branco",
        "Europe/Lisbon",
        "Atlantic/Madeira",
        "Atlantic/Azores",
    }
)

_CEP_PATTERN = re.compile(r"^\d{5}-\d{3}$")


class AccountUpdateRequest(BaseModel):
    name: str
    alternate_name: str
    identification: str
    country: str = "BRASIL"
    state: str
    city: str
    postal_code: str
    street: str
    region: str
    cellphone: str
    phone: str
    email: EmailStr
    email_admin: EmailStr
    site: str | None = None
    timezone: str = DEFAULT_TIMEZONE

    @field_validator("identification")
    @classmethod
    def _validate_identification(cls, value: str) -> str:
        # Regra 1: formato aceito com ou sem máscara, armazenado sem.
        if not is_valid_cpf_or_cnpj(value):
            raise ValueError("CPF/CNPJ inválido.")
        return strip_document_mask(value)

    @field_validator("postal_code")
    @classmethod
    def _validate_postal_code(cls, value: str) -> str:
        if not _CEP_PATTERN.match(value):
            raise ValueError("CEP deve estar no formato 99999-999.")
        return value

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        if value not in ALLOWED_TIMEZONES:
            raise ValueError(
                "Timezone inválido — precisa ser um de: " + ", ".join(sorted(ALLOWED_TIMEZONES))
            )
        return value


class PublicationsSettingsResponse(BaseModel):
    default_publications_user_id: uuid.UUID | None


class PublicationsSettingsUpdateRequest(BaseModel):
    """Rota 3 do roteamento de intimações (spec 045, §5) — responsável geral."""

    default_publications_user_id: uuid.UUID | None = None


class AccountResponse(BaseModel):
    id: uuid.UUID
    name: str
    alternate_name: str
    identification: str
    country: str
    state: str
    city: str
    postal_code: str
    street: str
    region: str
    cellphone: str
    phone: str
    email: str
    email_admin: str
    site: str | None
    timezone: str
    logo_url: str | None
    plan: AccountPlan
    track_access_logs: bool
    created_at: datetime
    updated_at: datetime


class AccountPlanUpdateRequest(BaseModel):
    plan: AccountPlan


class AccountStorageResponse(BaseModel):
    used_bytes: int
    quota_bytes: int
    plan: AccountPlan


class AccessTrackingResponse(BaseModel):
    track_access_logs: bool


class AccessTrackingUpdateRequest(BaseModel):
    enabled: bool


class AiSettingsRequest(BaseModel):
    """Spec 086 §5."""

    ai_auto_read_publications: bool


class AiSettingsResponse(BaseModel):
    ai_auto_read_publications: bool
