import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http import get_or_404
from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.publications.exceptions import (
    LawsuitNotFoundError,
    PublicationAlreadyExistsError,
)
from app.domain.publications.metrics import PublicationMetricsService
from app.domain.publications.models import Publication
from app.domain.publications.repository import PublicationListRow
from app.domain.publications.routing import PublicationRoutingService
from app.domain.publications.schemas import (
    LinkPublicationRequest,
    PublicationCountsResponse,
    PublicationDetailResponse,
    PublicationExportRequest,
    PublicationFilters,
    PublicationImportRequest,
    PublicationLawyerResponse,
    PublicationListItemResponse,
    PublicationListResponse,
    PublicationMetricsResponse,
    PublicationRecipientResponse,
    PublicationResponse,
)
from app.domain.publications.service import PublicationDetail, PublicationService
from app.domain.users.models import User
from app.integrations.djen.parser import DjenParseError, parse_communication

router = APIRouter(prefix="/publications", tags=["publications"])

_NOT_FOUND_DETAIL = "Publicação não encontrada."
_DEFAULT_PAGE_SIZE = 20


def _publication_to_response(publication: Publication) -> PublicationResponse:
    return PublicationResponse(
        id=publication.id,
        external_id=publication.external_id,
        hash=publication.hash,
        availability_date=publication.availability_date,
        court_code=publication.court_code,
        communication_type=publication.communication_type,
        process_number=publication.process_number,
        status=publication.status,
        is_active=publication.is_active,
        lawsuit_id=publication.lawsuit_id,
        created_at=publication.created_at,
        post_id=publication.post_id,
        matched_by=publication.matched_by,
        routed_to=publication.routed_to,
        routed_by=publication.routed_by,
        processed_at=publication.processed_at,
    )


def _row_to_item_response(row: PublicationListRow) -> PublicationListItemResponse:
    publication = row.publication
    return PublicationListItemResponse(
        id=publication.id,
        availability_date=publication.availability_date,
        court_code=publication.court_code,
        organ_name=publication.organ_name,
        process_number=publication.process_number,
        parties=row.parties,
        routed_to=publication.routed_to,
        routed_to_name=row.routed_to_name,
        lawsuit_id=publication.lawsuit_id,
        is_active=publication.is_active,
        cancellation_reason=publication.cancellation_reason,
        is_read=row.is_read,
    )


def _detail_to_response(detail: PublicationDetail) -> PublicationDetailResponse:
    publication = detail.publication
    return PublicationDetailResponse(
        id=publication.id,
        external_id=publication.external_id,
        availability_date=publication.availability_date,
        court_code=publication.court_code,
        communication_type=publication.communication_type,
        document_type=publication.document_type,
        organ_name=publication.organ_name,
        body=publication.body,
        process_number=publication.process_number,
        link=publication.link,
        status=publication.status,
        is_active=publication.is_active,
        cancellation_reason=publication.cancellation_reason,
        cancelled_at=publication.cancelled_at,
        lawsuit_id=publication.lawsuit_id,
        post_id=publication.post_id,
        matched_by=publication.matched_by,
        routed_to=publication.routed_to,
        routed_by=publication.routed_by,
        created_at=publication.created_at,
        recipients=[
            PublicationRecipientResponse(name=recipient.name, pole=recipient.pole)
            for recipient in detail.recipients
        ],
        lawyers=[
            PublicationLawyerResponse(
                name=lawyer.name, oab_number=lawyer.oab_number, oab_state=lawyer.oab_state
            )
            for lawyer in detail.lawyers
        ],
        is_read=detail.is_read,
    )


@router.post("", status_code=201)
async def import_publication(
    payload: PublicationImportRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PublicationResponse:
    """Registro manual de uma comunicação do DJEN a partir do item bruto.

    A captura em lote é do worker (spec 044); este endpoint existe para registro
    avulso e reprocessamento de `raw_payload` sem rebater no DJEN.
    """
    try:
        parsed = parse_communication(payload.item)
    except DjenParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    service = PublicationService(session=session, tenant_id=current_user.tenant_id)
    try:
        publication = await service.register(parsed)
    except PublicationAlreadyExistsError as exc:
        raise HTTPException(
            status_code=409, detail="Já existe uma publicação com esse hash."
        ) from exc
    routing = PublicationRoutingService(session=session, tenant_id=current_user.tenant_id)
    routed = await routing.route(publication)
    return _publication_to_response(routed)


@router.get("")
async def list_publications(
    interval: Literal["today", "3d", "7d", "custom"] = Query(default="7d"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    user_id: uuid.UUID | None = Query(default=None),
    customer_id: uuid.UUID | None = Query(default=None),
    court_code: str | None = Query(default=None),
    process_number: str | None = Query(default=None),
    linked: bool | None = Query(default=None),
    cancelled: bool | None = Query(default=None),
    read: bool | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=100),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PublicationListResponse:
    filters = PublicationFilters(
        interval=interval,
        date_from=date_from,
        date_to=date_to,
        user_id=user_id,
        customer_id=customer_id,
        court_code=court_code,
        process_number=process_number,
        linked=linked,
        cancelled=cancelled,
        read=read,
    )
    service = PublicationService(session=session, tenant_id=current_user.tenant_id)
    rows, next_cursor, total = await service.list_publications(
        filters=filters, current_user_id=current_user.id, cursor=cursor, limit=limit
    )
    return PublicationListResponse(
        items=[_row_to_item_response(row) for row in rows], next_cursor=next_cursor, total=total
    )


@router.get("/counts")
async def get_publication_counts(
    interval: Literal["today", "3d", "7d", "custom"] = Query(default="7d"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    user_id: uuid.UUID | None = Query(default=None),
    customer_id: uuid.UUID | None = Query(default=None),
    court_code: str | None = Query(default=None),
    process_number: str | None = Query(default=None),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PublicationCountsResponse:
    """Regra do §8: total/não vinculadas/canceladas/não lidas numa query só —
    os toggles (`linked`/`cancelled`/`read`) não entram aqui, são o que se conta."""
    filters = PublicationFilters(
        interval=interval,
        date_from=date_from,
        date_to=date_to,
        user_id=user_id,
        customer_id=customer_id,
        court_code=court_code,
        process_number=process_number,
    )
    service = PublicationService(session=session, tenant_id=current_user.tenant_id)
    counts = await service.get_counts(filters=filters, current_user_id=current_user.id)
    return PublicationCountsResponse(
        total=counts.total,
        unlinked=counts.unlinked,
        cancelled=counts.cancelled,
        unread=counts.unread,
    )


@router.get("/metrics")
async def get_publication_metrics(
    period: int = Query(default=7, ge=1, le=90),
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PublicationMetricsResponse:
    """Spec 049, §5/§7: publicações por dia/tribunal e taxa de vínculo automático."""
    service = PublicationMetricsService(session=session, tenant_id=current_user.tenant_id)
    metrics = await service.get_metrics(period_days=period)
    return PublicationMetricsResponse(
        period_days=metrics.period_days,
        total=metrics.total,
        auto_linked=metrics.auto_linked,
        auto_link_rate=metrics.auto_link_rate,
        per_day={day.isoformat(): count for day, count in metrics.per_day.items()},
        per_court=metrics.per_court,
    )


@router.post("/export")
async def export_publications(
    payload: PublicationExportRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> Response:
    service = PublicationService(session=session, tenant_id=current_user.tenant_id)
    content = await service.export(
        format_=payload.format, filters=payload.filters, current_user_id=current_user.id
    )
    media_type = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if payload.format == "xlsx"
        else "application/pdf"
    )
    filename = f"intimacoes.{payload.format}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{publication_id}")
async def get_publication(
    publication_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PublicationDetailResponse:
    """Regra 4: inteiro teor — consumido pelo drawer lateral do front."""
    service = PublicationService(session=session, tenant_id=current_user.tenant_id)
    publication = await get_or_404(lambda: service.get_by_id(publication_id), _NOT_FOUND_DETAIL)
    detail = await service.get_detail(publication, current_user_id=current_user.id)
    return _detail_to_response(detail)


@router.post("/{publication_id}/read")
async def mark_publication_read(
    publication_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PublicationDetailResponse:
    """Regra 5: leitura é por usuário."""
    service = PublicationService(session=session, tenant_id=current_user.tenant_id)
    publication = await get_or_404(lambda: service.get_by_id(publication_id), _NOT_FOUND_DETAIL)
    await service.mark_read(publication, current_user.id)
    detail = await service.get_detail(publication, current_user_id=current_user.id)
    return _detail_to_response(detail)


@router.post("/{publication_id}/link")
async def link_publication(
    publication_id: uuid.UUID,
    payload: LinkPublicationRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PublicationResponse:
    """Vínculo manual (spec 045, regra 7): dispara o roteamento e cria a tarefa."""
    service = PublicationService(session=session, tenant_id=current_user.tenant_id)
    publication = await get_or_404(lambda: service.get_by_id(publication_id), _NOT_FOUND_DETAIL)
    routing = PublicationRoutingService(session=session, tenant_id=current_user.tenant_id)
    try:
        linked = await routing.link(publication, payload.lawsuit_id)
    except LawsuitNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Processo não encontrado.") from exc
    return _publication_to_response(linked)


@router.post("/{publication_id}/reprocess")
async def reprocess_publication(
    publication_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PublicationResponse:
    """Regra 1: reprocessar não duplica a tarefa já criada."""
    service = PublicationService(session=session, tenant_id=current_user.tenant_id)
    publication = await get_or_404(lambda: service.get_by_id(publication_id), _NOT_FOUND_DETAIL)
    routing = PublicationRoutingService(session=session, tenant_id=current_user.tenant_id)
    reprocessed = await routing.reprocess(publication)
    return _publication_to_response(reprocessed)
