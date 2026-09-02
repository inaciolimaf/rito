import uuid
from datetime import date, datetime

from pydantic import BaseModel, model_validator

from app.core.br_documents import is_valid_cnpj, is_valid_cpf, strip_document_mask
from app.domain.monitored_terms.models import TermKind, TermStatus

BACKFILL_DEFAULT_DAYS = 30  # regra 6: padrão 30 dias atrás
BACKFILL_MAX_DAYS = 365  # regra 6: máximo 12 meses
SYNC_RUN_RETENTION_DAYS = 90  # spec 049, regra 9


def _validated_oab(bruto: str, digits: str, uf: str | None) -> str:
    """Regra 1: OAB é só número e exige UF, devolvida em maiúsculas.

    A checagem `bruto != digits` é o que distingue OAB de CPF/CNPJ: nos outros dois a
    máscara é aceita e removida, aqui um caractere não numérico é erro — porque "12345/SP"
    digitado no campo do número é UF no lugar errado, não formatação.
    """
    if bruto.strip() != digits:
        raise ValueError("Número de OAB deve conter apenas dígitos.")
    if not uf:
        raise ValueError("UF da OAB é obrigatória.")
    return uf.upper()


class MonitoredTermCreateRequest(BaseModel):
    kind: TermKind
    value: str
    oab_state: str | None = None
    label: str | None = None
    user_id: uuid.UUID | None = None
    backfill_from: date | None = None

    @model_validator(mode="after")
    def validate_by_kind(self) -> "MonitoredTermCreateRequest":
        # Regra 1: OAB é só números e exige UF. Regra 2: CPF/CNPJ pelo algoritmo
        # real (018). O banco guarda só dígitos nos três casos.
        digits = strip_document_mask(self.value)
        if not digits:
            raise ValueError("Informe o número do termo.")
        if self.kind is TermKind.OAB:
            self.oab_state = _validated_oab(self.value, digits, self.oab_state)
        elif self.kind is TermKind.CPF and not is_valid_cpf(digits):
            raise ValueError("CPF inválido.")
        elif self.kind is TermKind.CNPJ and not is_valid_cnpj(digits):
            raise ValueError("CNPJ inválido.")
        self.value = digits
        # Regra 6 (o teto de 12 meses) mora no service desde a spec 114: aqui não há fuso
        # do escritório, e "12 meses atrás" medido no relógio do servidor é a mesma classe
        # de erro que a spec veio consertar.
        return self


class MonitoredTermUpdateRequest(BaseModel):
    label: str | None = None
    user_id: uuid.UUID | None = None
    backfill_from: date | None = None
    is_active: bool = True


class MonitoredTermResponse(BaseModel):
    id: uuid.UUID
    kind: TermKind
    value: str
    oab_state: str | None
    label: str | None
    user_id: uuid.UUID | None
    status: TermStatus
    status_message: str | None
    last_sync_at: datetime | None
    last_success_at: datetime | None
    next_sync_at: datetime | None
    backfill_from: date | None
    is_active: bool
    created_at: datetime
    captured_count: int = 0
    consecutive_failures: int = 0


class MonitoredTermListResponse(BaseModel):
    items: list[MonitoredTermResponse]
    total: int


class TermHealthResponse(BaseModel):
    """Spec 049, §5 — o `TermHealthCard` do front; o histórico completo de
    execuções continua em `GET /{id}/runs` (spec 043/044), não duplicado aqui."""

    id: uuid.UUID
    status: TermStatus
    consecutive_failures: int
    last_sync_at: datetime | None
    last_success_at: datetime | None
    next_sync_at: datetime | None
    alert_id: uuid.UUID | None


class TermSyncRunResponse(BaseModel):
    id: uuid.UUID
    started_at: datetime
    finished_at: datetime | None
    found_count: int
    new_count: int
    error: str | None


class TermSyncRunListResponse(BaseModel):
    items: list[TermSyncRunResponse]
    next_cursor: str | None
    total: int
