import re
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, EmailStr, field_validator, model_validator

from app.core.br_documents import BRAZILIAN_UFS
from app.domain.users.models import FinancialAccess, UserRole

_OAB_PATTERN = re.compile(r"^\d{4,6}/([A-Z]{2})$")


def _validate_oab_format(value: str) -> str:
    match = _OAB_PATTERN.match(value)
    if not match or match.group(1) not in BRAZILIAN_UFS:
        raise ValueError("OAB deve estar no formato NNNNNN/UF, com UF válida.")
    return value


class OccupationResponse(BaseModel):
    id: int
    name: str


class UserUpdateRequest(BaseModel):
    name: str
    role: UserRole
    financial_access: FinancialAccess
    occupation_id: int | None = None
    identification: str | None = None
    document: str | None = None
    birthdate: date | None = None
    number_ctps: str | None = None
    number_oab: str | None = None
    cellphone: str | None = None
    phone: str | None = None
    salary: Decimal | None = None
    admission_date: date | None = None
    resignation_date: date | None = None
    work_start: time | None = None
    work_interval: timedelta | None = None
    work_end: time | None = None
    points_goal: int | None = None
    report_deadline: bool = False
    report_deleted: bool = False
    is_responsible: bool = False

    @field_validator("number_oab")
    @classmethod
    def _validate_number_oab(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _validate_oab_format(value)

    @model_validator(mode="after")
    def _validate_work_schedule(self) -> "UserUpdateRequest":
        # Regra 5: work_end > work_start; intervalo menor que a jornada total.
        if self.work_start is not None and self.work_end is not None:
            if self.work_end <= self.work_start:
                raise ValueError("work_end deve ser depois de work_start.")
            if self.work_interval is not None:
                total = datetime.combine(date.min, self.work_end) - datetime.combine(
                    date.min, self.work_start
                )
                if self.work_interval >= total:
                    raise ValueError("O intervalo precisa ser menor que a jornada total.")

        # Regra 6: resignation_date >= admission_date.
        if (
            self.admission_date is not None
            and self.resignation_date is not None
            and self.resignation_date < self.admission_date
        ):
            raise ValueError("resignation_date não pode ser antes de admission_date.")

        return self


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    is_active: bool
    role: UserRole
    financial_access: FinancialAccess
    occupation_id: int | None
    identification: str | None
    document: str | None
    birthdate: date | None
    number_ctps: str | None
    number_oab: str | None
    cellphone: str | None
    phone: str | None
    avatar_url: str | None
    salary: Decimal | None
    admission_date: date | None
    resignation_date: date | None
    work_start: time | None
    work_interval: timedelta | None
    work_end: time | None
    points_goal: int | None
    report_deadline: bool
    report_deleted: bool
    is_responsible: bool
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseModel):
    items: list[UserResponse]
    next_cursor: str | None
    total: int


class InviteUserRequest(BaseModel):
    email: EmailStr
    role: UserRole
    financial_access: FinancialAccess = FinancialAccess.NONE
    occupation_id: int | None = None


class InviteUserResponse(BaseModel):
    id: uuid.UUID
    email: str
    role: UserRole
    expires_at: datetime


class AcceptInvitationRequest(BaseModel):
    token: str
    name: str
    password: str


class PointsGoalRequest(BaseModel):
    """Meta mensal de pontos (spec 039 §5) — None = sem meta (a UI mostra "—", regra 3)."""

    points_goal: int | None = None


class PreferencesResponse(BaseModel):
    # Any com justificativa: preferências são chave/valor livre por design (JSONB) —
    # o servidor não conhece a forma de cada chave; quem valida é o consumidor.
    preferences: dict[str, Any]


class PreferencesUpdateRequest(BaseModel):
    preferences: dict[str, Any]


class MentionableUserResponse(BaseModel):
    """Forma mínima para o autocomplete de @menção (spec 035) — só id e nome."""

    id: uuid.UUID
    name: str
