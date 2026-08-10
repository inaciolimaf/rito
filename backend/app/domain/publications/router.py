from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.publications.exceptions import PublicationAlreadyExistsError
from app.domain.publications.models import Publication
from app.domain.publications.schemas import PublicationImportRequest, PublicationResponse
from app.domain.publications.service import PublicationService
from app.domain.users.models import User
from app.integrations.djen.parser import DjenParseError, parse_communication

router = APIRouter(prefix="/publications", tags=["publications"])


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
    )


@router.post("", status_code=201)
async def import_publication(
    payload: PublicationImportRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PublicationResponse:
    """Registro manual de uma comunicação do DJEN a partir do item bruto.

    A captura em lote é do worker (spec 044); este endpoint existe para registro
    avulso e reprocessamento de `raw_payload` sem rebater na API.
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
    return _publication_to_response(publication)
