import uuid
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http import get_or_404
from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.lawsuits.exceptions import (
    CourtSystemIncompatibleError,
    DuplicatePartyError,
    LastPartyError,
    LawsuitTypeNotFoundError,
    PartyCustomerNotFoundError,
    ResponsibleNotActiveError,
    StageNotFoundError,
)
from app.domain.lawsuits.schemas import (
    LawsuitCreateRequest,
    LawsuitResponse,
    LawsuitUpdateRequest,
    PartyCreateRequest,
    PartyResponse,
    PartyUpdateRequest,
)
from app.domain.lawsuits.service import LawsuitDetail, LawsuitService, PartyDetail
from app.domain.users.models import User

router = APIRouter(prefix="/lawsuits", tags=["lawsuits"])

_NOT_FOUND_DETAIL = "Processo não encontrado."
_PARTY_NOT_FOUND_DETAIL = "Parte não encontrada."
_PARTY_CUSTOMER_DETAIL = "Contato não encontrado."
_DUPLICATE_PARTY_DETAIL = "Esta pessoa já está neste polo do processo."
_LAST_PARTY_DETAIL = "O processo precisa de pelo menos uma parte."


def _raise_party_errors(exc: Exception) -> NoReturn:
    if isinstance(exc, PartyCustomerNotFoundError):
        raise HTTPException(status_code=422, detail=_PARTY_CUSTOMER_DETAIL) from exc
    if isinstance(exc, DuplicatePartyError):
        raise HTTPException(status_code=409, detail=_DUPLICATE_PARTY_DETAIL) from exc
    raise exc


def _to_party_response(detail: PartyDetail) -> PartyResponse:
    party = detail.party
    return PartyResponse(
        id=party.id,
        lawsuit_id=party.lawsuit_id,
        customer_id=party.customer_id,
        customer_name=detail.customer_name,
        pole=party.pole,
        is_client=party.is_client,
        created_at=party.created_at,
    )


def _to_response(detail: LawsuitDetail) -> LawsuitResponse:
    lawsuit = detail.lawsuit
    return LawsuitResponse(
        id=lawsuit.id,
        user_id=lawsuit.user_id,
        lawsuit_type_id=lawsuit.lawsuit_type_id,
        action_group_id=detail.action_group_id,
        action_group_name=detail.action_group_name,
        stage_id=lawsuit.stage_id,
        step_id=detail.step_id,
        step_name=detail.step_name,
        court_id=lawsuit.court_id,
        court_system_id=lawsuit.court_system_id,
        process_number=lawsuit.process_number,
        protocol_number=lawsuit.protocol_number,
        originating_process=lawsuit.originating_process,
        folder=lawsuit.folder,
        filing_year=lawsuit.filing_year,
        judiciary=lawsuit.judiciary,
        county=lawsuit.county,
        court_division=lawsuit.court_division,
        process_date=lawsuit.process_date,
        notes=lawsuit.notes,
        is_archived=lawsuit.is_archived,
        created_at=lawsuit.created_at,
        updated_at=lawsuit.updated_at,
    )


@router.post("", status_code=201)
async def create_lawsuit(
    payload: LawsuitCreateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> LawsuitResponse:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    try:
        created = await service.create(payload)
    except LawsuitTypeNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Tipo de ação não encontrado.") from exc
    except StageNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Etapa não encontrada.") from exc
    except ResponsibleNotActiveError as exc:
        raise HTTPException(
            status_code=422, detail="Responsável precisa ser um usuário ativo do tenant."
        ) from exc
    except CourtSystemIncompatibleError as exc:
        raise HTTPException(
            status_code=422, detail="Sistema processual não pertence ao tribunal selecionado."
        ) from exc
    except (PartyCustomerNotFoundError, DuplicatePartyError) as exc:
        _raise_party_errors(exc)
    return _to_response(created)


@router.get("/{lawsuit_id}")
async def get_lawsuit(
    lawsuit_id: uuid.UUID,
    _current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> LawsuitResponse:
    service = LawsuitService(session=session, tenant_id=_current_user.tenant_id)
    detail = await get_or_404(lambda: service.get(lawsuit_id), _NOT_FOUND_DETAIL)
    return _to_response(detail)


@router.put("/{lawsuit_id}")
async def update_lawsuit(
    lawsuit_id: uuid.UUID,
    payload: LawsuitUpdateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> LawsuitResponse:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(lambda: service.get(lawsuit_id), _NOT_FOUND_DETAIL)
    try:
        updated = await service.update(detail.lawsuit, payload)
    except LawsuitTypeNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Tipo de ação não encontrado.") from exc
    except StageNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Etapa não encontrada.") from exc
    except ResponsibleNotActiveError as exc:
        raise HTTPException(
            status_code=422, detail="Responsável precisa ser um usuário ativo do tenant."
        ) from exc
    except CourtSystemIncompatibleError as exc:
        raise HTTPException(
            status_code=422, detail="Sistema processual não pertence ao tribunal selecionado."
        ) from exc
    return _to_response(updated)


@router.delete("/{lawsuit_id}", status_code=204)
async def delete_lawsuit(
    lawsuit_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> None:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(lambda: service.get(lawsuit_id), _NOT_FOUND_DETAIL)
    await service.delete(detail.lawsuit)


@router.get("/{lawsuit_id}/parties")
async def list_parties(
    lawsuit_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> list[PartyResponse]:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(lambda: service.get(lawsuit_id), _NOT_FOUND_DETAIL)
    parties = await service.list_parties(detail.lawsuit.id)
    return [_to_party_response(party) for party in parties]


@router.post("/{lawsuit_id}/parties", status_code=201)
async def add_party(
    lawsuit_id: uuid.UUID,
    payload: PartyCreateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PartyResponse:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(lambda: service.get(lawsuit_id), _NOT_FOUND_DETAIL)
    try:
        party = await service.add_party(detail.lawsuit, payload)
    except (PartyCustomerNotFoundError, DuplicatePartyError) as exc:
        _raise_party_errors(exc)
    return _to_party_response(party)


async def _get_party_or_404(
    service: LawsuitService, lawsuit_id: uuid.UUID, party_id: uuid.UUID
) -> PartyDetail:
    detail = await get_or_404(lambda: service.get(lawsuit_id), _NOT_FOUND_DETAIL)
    party = await service.parties.get_by_id(party_id)
    if party is None or party.lawsuit_id != detail.lawsuit.id:
        raise HTTPException(status_code=404, detail=_PARTY_NOT_FOUND_DETAIL)
    customer = await service.customers.get_by_id(party.customer_id)
    if customer is None:
        # FK garante que o contato existe; None aqui só aconteceria com RLS mal aplicado.
        raise HTTPException(status_code=404, detail=_PARTY_NOT_FOUND_DETAIL)
    return PartyDetail(party=party, customer_name=customer.name)


@router.put("/{lawsuit_id}/parties/{party_id}")
async def update_party(
    lawsuit_id: uuid.UUID,
    party_id: uuid.UUID,
    payload: PartyUpdateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PartyResponse:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    detail = await _get_party_or_404(service, lawsuit_id, party_id)
    try:
        updated = await service.update_party(detail.party, payload)
    except (PartyCustomerNotFoundError, DuplicatePartyError) as exc:
        _raise_party_errors(exc)
    return _to_party_response(updated)


@router.delete("/{lawsuit_id}/parties/{party_id}", status_code=204)
async def remove_party(
    lawsuit_id: uuid.UUID,
    party_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> None:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    detail = await _get_party_or_404(service, lawsuit_id, party_id)
    try:
        await service.remove_party(detail.party)
    except LastPartyError as exc:
        raise HTTPException(status_code=409, detail=_LAST_PARTY_DETAIL) from exc
