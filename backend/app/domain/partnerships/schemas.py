import uuid
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field

from app.core.schemas import JsonDecimal
from app.domain.partnerships.models import PartnershipStatus


class PartnershipInviteRequest(BaseModel):
    email: EmailStr


class PartnershipAcceptRequest(BaseModel):
    token: str


class PartnershipResponse(BaseModel):
    id: uuid.UUID
    status: PartnershipStatus
    invited_email: str
    # Ponto de vista do escritório da sessão: quem convidou vê o convidado e vice-versa.
    partner_tenant_id: uuid.UUID | None
    partner_name: str | None
    is_requester: bool
    shared_count: int
    accepted_at: datetime | None
    created_at: datetime


class PartnershipListResponse(BaseModel):
    items: list[PartnershipResponse]
    total: int


class PartnershipInviteResponse(BaseModel):
    partnership: PartnershipResponse
    # Regra 2: e-mail sem conta no Rito recebe convite de CADASTRO — a UI avisa que a
    # parceria só fica ativa depois que o escritório convidado criar a conta.
    account_exists: bool
    # Sem `token`: desde a spec 102 (regra 19) o link vai por e-mail. Ver o comentário
    # em `invite_partner`.


class ShareLawsuitRequest(BaseModel):
    partnership_id: uuid.UUID
    can_view_financial: bool = False
    can_create_tasks: bool = True


class SharedLawsuitResponse(BaseModel):
    id: uuid.UUID
    lawsuit_id: uuid.UUID
    partnership_id: uuid.UUID
    partner_tenant_id: uuid.UUID
    partner_name: str | None
    can_view_financial: bool
    can_create_tasks: bool
    revoked_at: datetime | None
    created_at: datetime


class SharedLawsuitListResponse(BaseModel):
    items: list[SharedLawsuitResponse]
    total: int


class SharedWithMeItem(BaseModel):
    """O processo do parceiro como o outro escritório o enxerga: identificação, fase e
    demanda em aberto. Valor de causa e honorários só vêm com `can_view_financial`
    (regra 9) — quando não vêm, vêm nulos do próprio banco."""

    share_id: uuid.UUID
    lawsuit_id: uuid.UUID
    partnership_id: uuid.UUID
    owner_tenant_id: uuid.UUID
    owner_name: str
    process_number: str | None
    folder: str | None
    stage_name: str
    step_id: int
    can_view_financial: bool
    can_create_tasks: bool
    case_value: JsonDecimal | None
    fees_value: JsonDecimal | None
    open_tasks: int
    shared_at: datetime


class SharedWithMeReport(BaseModel):
    lawsuits_by_step: dict[str, int]
    open_tasks: int


class SharedWithMeResponse(BaseModel):
    items: list[SharedWithMeItem]
    total: int
    report: SharedWithMeReport | None = None


class SharedPartyResponse(BaseModel):
    pole: str
    name: str
    is_client: bool


class SharedMovementResponse(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    title: str
    body: str | None
    origin: str


class SharedTaskResponse(BaseModel):
    id: uuid.UUID
    task_type_name: str
    scheduled_date: date | None
    deadline_date: date | None
    comments: str | None
    completed: bool
    from_partner: bool
    created_at: datetime


class SharedLawsuitDetailResponse(BaseModel):
    lawsuit: SharedWithMeItem
    parties: list[SharedPartyResponse]
    timeline: list[SharedMovementResponse]
    tasks: list[SharedTaskResponse]


class SharedTaskTypeResponse(BaseModel):
    id: uuid.UUID
    name: str


class PartnerTaskCreateRequest(BaseModel):
    task_type_id: uuid.UUID
    scheduled_date: date | None = None
    deadline_date: date | None = None
    comments: str | None = Field(default=None, max_length=2000)


class PartnershipSummaryResponse(BaseModel):
    """Os três cards da tela (spec 079 §6)."""

    shared_lawsuits: int
    pending_by_office: int
    pending_by_partner: int
    active_partners: int
