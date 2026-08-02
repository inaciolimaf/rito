import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http import get_or_404
from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.lawsuits.exceptions import (
    CourtSystemIncompatibleError,
    LawsuitTypeNotFoundError,
    ResponsibleNotActiveError,
    StageNotFoundError,
)
from app.domain.lawsuits.schemas import LawsuitCreateRequest, LawsuitResponse, LawsuitUpdateRequest
from app.domain.lawsuits.service import LawsuitDetail, LawsuitService
from app.domain.users.models import User

router = APIRouter(prefix="/lawsuits", tags=["lawsuits"])

_NOT_FOUND_DETAIL = "Processo não encontrado."


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
