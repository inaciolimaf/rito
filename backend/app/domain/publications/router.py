import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http import get_or_404
from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.publications.exceptions import (
    LawsuitNotFoundError,
    PublicationAlreadyExistsError,
)
from app.domain.publications.models import Publication
from app.domain.publications.repository import PublicationRepository
from app.domain.publications.routing import PublicationRoutingService
from app.domain.publications.schemas import (
    LinkPublicationRequest,
    PublicationImportRequest,
    PublicationResponse,
)
from app.domain.publications.service import PublicationService
from app.domain.users.models import User
from app.integrations.djen.parser import DjenParseError, parse_communication

router = APIRouter(prefix="/publications", tags=["publications"])

_NOT_FOUND_DETAIL = "Publicação não encontrada."


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


@router.post("/{publication_id}/link")
async def link_publication(
    publication_id: uuid.UUID,
    payload: LinkPublicationRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PublicationResponse:
    """Vínculo manual (spec 045, regra 7): dispara o roteamento e cria a tarefa."""
    publications = PublicationRepository(session)
    publication = await get_or_404(
        lambda: publications.get_by_id(publication_id), _NOT_FOUND_DETAIL
    )
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
    publications = PublicationRepository(session)
    publication = await get_or_404(
        lambda: publications.get_by_id(publication_id), _NOT_FOUND_DETAIL
    )
    routing = PublicationRoutingService(session=session, tenant_id=current_user.tenant_id)
    reprocessed = await routing.reprocess(publication)
    return _publication_to_response(reprocessed)
