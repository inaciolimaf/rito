import uuid
from typing import Literal, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http import get_or_404
from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.lawsuits.cnj import SEGMENT_NAMES, CNJValidationError
from app.domain.lawsuits.exceptions import (
    CourtSystemIncompatibleError,
    DuplicatePartyError,
    LastPartyError,
    LawsuitTypeNotFoundError,
    MovementNotAuthorError,
    PartyCustomerNotFoundError,
    ResponsibleNotActiveError,
    StageNotFoundError,
    TribunalMovementImmutableError,
)
from app.domain.lawsuits.export import build_pdf, build_xlsx
from app.domain.lawsuits.listing import LawsuitListRow
from app.domain.lawsuits.models import LawsuitMovement
from app.domain.lawsuits.repository import TIMELINE_KINDS
from app.domain.lawsuits.schemas import (
    FinancialSummaryResponse,
    InferredCourtResponse,
    LawsuitCreateRequest,
    LawsuitExportRequest,
    LawsuitFiltersQuery,
    LawsuitListItemResponse,
    LawsuitListResponse,
    LawsuitResponse,
    LawsuitUpdateRequest,
    MovementCreateRequest,
    MovementResponse,
    MovementUpdateRequest,
    ParsedCNJResponse,
    PartyBriefResponse,
    PartyCreateRequest,
    PartyResponse,
    PartyUpdateRequest,
    TimelineItemResponse,
    TimelineResponse,
    ValidateNumberRequest,
    ValidateNumberResponse,
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


def _to_list_item_response(row: LawsuitListRow) -> LawsuitListItemResponse:
    lawsuit = row.lawsuit
    return LawsuitListItemResponse(
        id=lawsuit.id,
        process_number=lawsuit.process_number,
        folder=lawsuit.folder,
        is_archived=lawsuit.is_archived,
        created_at=lawsuit.created_at,
        last_movement_at=lawsuit.last_movement_at,
        last_movement_title=row.last_movement_title,
        lawsuit_type_name=row.lawsuit_type_name,
        action_group_name=row.action_group_name,
        stage_name=row.stage_name,
        parties=[
            PartyBriefResponse(name=str(party["name"]), pole=party["pole"]) for party in row.parties
        ],
        parties_total=row.parties_total,
    )


def _to_movement_response(movement: LawsuitMovement) -> MovementResponse:
    return MovementResponse(
        id=movement.id,
        lawsuit_id=movement.lawsuit_id,
        origin=movement.origin,
        occurred_at=movement.occurred_at,
        title=movement.title,
        body=movement.body,
        header=movement.header,
        external_code=movement.external_code,
        external_id=movement.external_id,
        created_by=movement.created_by,
        created_at=movement.created_at,
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
        case_value=lawsuit.case_value,
        fees_value=lawsuit.fees_value,
        fees_percentage=lawsuit.fees_percentage,
        contingency=lawsuit.contingency,
        closure_date=lawsuit.closure_date,
        transit_date=lawsuit.transit_date,
        archived_date=lawsuit.archived_date,
        outcome=lawsuit.outcome,
        is_archived=lawsuit.is_archived,
        created_at=lawsuit.created_at,
        updated_at=lawsuit.updated_at,
    )


@router.get("")
async def list_lawsuits(
    # Depends() (não Query()): nesta versão do FastAPI o modelo Pydantic só é expandido
    # em parâmetros de query individuais como dependência — com Query() o modelo inteiro
    # vira UM parâmetro obrigatório chamado "filters".
    filters: LawsuitFiltersQuery = Depends(),
    order: Literal["asc", "desc"] = Query(default="desc"),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> LawsuitListResponse:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    items, next_cursor, total = await service.list_lawsuits(
        payload=filters, order=order, cursor=cursor, limit=limit
    )
    return LawsuitListResponse(
        items=[_to_list_item_response(item) for item in items],
        next_cursor=next_cursor,
        total=total,
    )


@router.post("/export")
async def export_lawsuits(
    payload: LawsuitExportRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> Response:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    rows = await service.export_lawsuits(payload=payload.filters)
    content = build_xlsx(rows) if payload.format == "xlsx" else build_pdf(rows)
    media_type = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if payload.format == "xlsx"
        else "application/pdf"
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="processos.{payload.format}"'},
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
    except CNJValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_response(created)


@router.post("/validate-number")
async def validate_number(
    payload: ValidateNumberRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> ValidateNumberResponse:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    result = await service.validate_number(payload.process_number)
    parsed = result.parsed
    return ValidateNumberResponse(
        valid=result.valid,
        formatted=result.formatted,
        parsed=(
            ParsedCNJResponse(
                sequential=parsed.sequential,
                check_digit=parsed.check_digit,
                year=parsed.year,
                segment=parsed.segment,
                segment_name=SEGMENT_NAMES[parsed.segment],
                court=parsed.court,
                origin=parsed.origin,
            )
            if parsed is not None
            else None
        ),
        inferred_court=(
            InferredCourtResponse(
                id=result.inferred_court.id,
                code=result.inferred_court.code,
                name=result.inferred_court.name,
            )
            if result.inferred_court is not None
            else None
        ),
        error=result.error,
    )


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
    except CNJValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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


@router.get("/{lawsuit_id}/financial-summary")
async def get_financial_summary(
    lawsuit_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> FinancialSummaryResponse:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(lambda: service.get(lawsuit_id), _NOT_FOUND_DETAIL)
    summary = service.financial_summary(detail.lawsuit)
    return FinancialSummaryResponse(
        case_value=summary.case_value,
        fees_value=summary.fees_value,
        received=summary.received,
        to_receive=summary.to_receive,
        expenses=summary.expenses,
        net_result=summary.net_result,
    )


@router.get("/{lawsuit_id}/timeline")
async def get_timeline(
    lawsuit_id: uuid.UUID,
    kinds: str | None = None,
    cursor: str | None = None,
    limit: int = 20,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> TimelineResponse:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(lambda: service.get(lawsuit_id), _NOT_FOUND_DETAIL)
    # Regra 2: toggles combináveis; `kinds=` vazio (nenhum marcado) → timeline vazia,
    # nunca a lista completa. Omitir o parâmetro traz todos os tipos.
    kind_list = TIMELINE_KINDS if kinds is None else [k for k in kinds.split(",") if k]
    page = await service.list_timeline(
        detail.lawsuit.id, kinds=kind_list, cursor=cursor, limit=min(limit, 100)
    )
    return TimelineResponse(
        items=[
            TimelineItemResponse(
                kind=item.kind,
                id=item.id,
                occurred_at=item.occurred_at,
                title=item.title,
                summary=item.summary,
                actor=item.actor,
                metadata={"header": item.header, "external_code": item.external_code},
            )
            for item in page.items
        ],
        next_cursor=page.next_cursor,
        total=page.total,
    )


@router.post("/{lawsuit_id}/movements", status_code=201)
async def create_movement(
    lawsuit_id: uuid.UUID,
    payload: MovementCreateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> MovementResponse:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(lambda: service.get(lawsuit_id), _NOT_FOUND_DETAIL)
    movement = await service.create_movement(detail.lawsuit, payload, current_user)
    return _to_movement_response(movement)


async def _get_movement_or_404(
    service: LawsuitService, lawsuit_id: uuid.UUID, movement_id: uuid.UUID
) -> LawsuitMovement:
    detail = await get_or_404(lambda: service.get(lawsuit_id), _NOT_FOUND_DETAIL)
    movement = await service.movements.get_by_id(movement_id)
    if movement is None or movement.lawsuit_id != detail.lawsuit.id:
        raise HTTPException(status_code=404, detail="Movimentação não encontrada.")
    return movement


@router.put("/{lawsuit_id}/movements/{movement_id}")
async def update_movement(
    lawsuit_id: uuid.UUID,
    movement_id: uuid.UUID,
    payload: MovementUpdateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> MovementResponse:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    movement = await _get_movement_or_404(service, lawsuit_id, movement_id)
    try:
        updated = await service.update_movement(movement, payload, current_user)
    except TribunalMovementImmutableError as exc:
        raise HTTPException(
            status_code=403, detail="Movimentação do tribunal não pode ser editada."
        ) from exc
    except MovementNotAuthorError as exc:
        raise HTTPException(
            status_code=403,
            detail="Só quem criou a movimentação (ou um administrador) pode editá-la.",
        ) from exc
    return _to_movement_response(updated)


@router.delete("/{lawsuit_id}/movements/{movement_id}", status_code=204)
async def delete_movement(
    lawsuit_id: uuid.UUID,
    movement_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> None:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    movement = await _get_movement_or_404(service, lawsuit_id, movement_id)
    try:
        await service.delete_movement(movement, current_user)
    except TribunalMovementImmutableError as exc:
        raise HTTPException(
            status_code=403, detail="Movimentação do tribunal não pode ser excluída."
        ) from exc
    except MovementNotAuthorError as exc:
        raise HTTPException(
            status_code=403,
            detail="Só quem criou a movimentação (ou um administrador) pode excluí-la.",
        ) from exc


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
