import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.domain.publications.models import Publication


@dataclass
class PublicationListRow:
    """Linha enriquecida (spec 048) — partes e nome do responsável resolvidos sem
    N+1, reaproveitada pela listagem e pelo export (mesmo padrão de `LawsuitListRow`,
    spec 027).

    Forma, não query: mora aqui desde a spec 118 (checagem 2), porque o router precisava
    dela só para anotar o mapeamento para a resposta HTTP e acabava importando a camada
    de dados por causa disso.
    """

    publication: Publication
    parties: list[str]
    routed_to_name: str | None
    is_read: bool


class PublicationImportRequest(BaseModel):
    """Item bruto de `items[]` do DJEN — o parse (integrations/djen) valida."""

    # Any: é o payload arbitrário da API externa; validar campo a campo aqui
    # duplicaria o parser (fonte única da verdade — spec 042, regra 10).
    item: dict[str, Any] = Field()


class PublicationResponse(BaseModel):
    id: uuid.UUID
    external_id: int
    hash: str
    availability_date: date
    court_code: str
    communication_type: str | None
    process_number: str | None
    status: str | None
    is_active: bool
    lawsuit_id: uuid.UUID | None
    created_at: datetime
    post_id: uuid.UUID | None
    matched_by: str | None
    routed_to: uuid.UUID | None
    routed_by: str | None
    processed_at: datetime | None


class LinkPublicationRequest(BaseModel):
    """Vínculo manual (spec 045, regra 7) — o usuário escolhe o processo."""

    lawsuit_id: uuid.UUID


class PublicationFilters(BaseModel):
    """Filtros da tela de intimações (spec 048, §5). `interval="custom"` exige
    `date_from`/`date_to`; os demais valores calculam o intervalo sozinhos."""

    interval: Literal["today", "3d", "7d", "custom"] = "7d"
    date_from: date | None = None
    date_to: date | None = None
    user_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    court_code: str | None = None
    process_number: str | None = None
    linked: bool | None = None
    cancelled: bool | None = None
    read: bool | None = None


class PublicationExportRequest(BaseModel):
    format: Literal["xlsx", "pdf"]
    filters: PublicationFilters = Field(default_factory=PublicationFilters)


class PublicationCountsResponse(BaseModel):
    total: int
    unlinked: int
    cancelled: int
    unread: int


class PublicationMetricsResponse(BaseModel):
    """Spec 049, §5/§7 — `per_day`/`per_court` chaveados por string pro JSON (a
    data vira ISO); "por termo" fica de fora (Descobertas da 049)."""

    period_days: int
    total: int
    auto_linked: int
    auto_link_rate: float | None
    per_day: dict[str, int]
    per_court: dict[str, int]


class PublicationListItemResponse(BaseModel):
    id: uuid.UUID
    availability_date: date
    court_code: str
    organ_name: str | None
    process_number: str | None
    parties: list[str]
    routed_to: uuid.UUID | None
    routed_to_name: str | None
    lawsuit_id: uuid.UUID | None
    is_active: bool
    cancellation_reason: str | None
    is_read: bool


class PublicationListResponse(BaseModel):
    items: list[PublicationListItemResponse]
    next_cursor: str | None = None
    total: int


class PublicationRecipientResponse(BaseModel):
    name: str
    pole: str | None


class PublicationLawyerResponse(BaseModel):
    name: str | None
    oab_number: str | None
    oab_state: str | None


class PublicationDetailResponse(BaseModel):
    id: uuid.UUID
    external_id: int
    availability_date: date
    court_code: str
    communication_type: str | None
    document_type: str | None
    organ_name: str | None
    body: str
    process_number: str | None
    link: str | None
    status: str | None
    is_active: bool
    cancellation_reason: str | None
    cancelled_at: date | None
    lawsuit_id: uuid.UUID | None
    post_id: uuid.UUID | None
    matched_by: str | None
    routed_to: uuid.UUID | None
    routed_by: str | None
    created_at: datetime
    recipients: list[PublicationRecipientResponse]
    lawyers: list[PublicationLawyerResponse]
    is_read: bool
