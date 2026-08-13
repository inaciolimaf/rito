import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.templates.exceptions import TemplateNotFoundError
from app.domain.templates.models import Template
from app.domain.templates.schemas import (
    TemplateCreateRequest,
    TemplateListResponse,
    TemplateResponse,
    TemplateUpdateRequest,
)
from app.domain.templates.service import TemplateService
from app.domain.users.models import User

router = APIRouter(tags=["templates"])

_DEFAULT_PAGE_SIZE = 20
_NOT_FOUND_DETAIL = "Modelo não encontrado."


def _to_response(template: Template) -> TemplateResponse:
    return TemplateResponse(
        id=template.id,
        name=template.name,
        type=template.type,
        content=template.content,
        created_by=template.created_by,
        deleted_at=template.deleted_at,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


@router.get("/templates")
async def list_templates(
    view: str = Query(default="all"),
    q: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=100),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> TemplateListResponse:
    service = TemplateService(session=session, tenant_id=current_user.tenant_id)
    try:
        items, next_cursor, total = await service.list_templates(
            view=view, query=q, cursor=cursor, limit=limit
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Tipo de modelo inválido.") from exc
    return TemplateListResponse(
        items=[_to_response(item) for item in items], next_cursor=next_cursor, total=total
    )


@router.post("/templates", status_code=201)
async def create_template(
    payload: TemplateCreateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> TemplateResponse:
    service = TemplateService(session=session, tenant_id=current_user.tenant_id)
    template = await service.create(
        current_user.id, name=payload.name, type_=payload.type, content=payload.content
    )
    return _to_response(template)


@router.get("/templates/{template_id}")
async def get_template(
    template_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> TemplateResponse:
    service = TemplateService(session=session, tenant_id=current_user.tenant_id)
    try:
        template = await service.get(template_id)
    except TemplateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL) from exc
    return _to_response(template)


@router.put("/templates/{template_id}")
async def update_template(
    template_id: uuid.UUID,
    payload: TemplateUpdateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> TemplateResponse:
    service = TemplateService(session=session, tenant_id=current_user.tenant_id)
    try:
        template = await service.update(
            template_id, name=payload.name, type_=payload.type, content=payload.content
        )
    except TemplateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL) from exc
    return _to_response(template)


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(
    template_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> None:
    service = TemplateService(session=session, tenant_id=current_user.tenant_id)
    try:
        await service.move_to_trash(template_id)
    except TemplateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL) from exc


@router.post("/templates/{template_id}/restore")
async def restore_template(
    template_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> TemplateResponse:
    service = TemplateService(session=session, tenant_id=current_user.tenant_id)
    try:
        template = await service.restore(template_id)
    except TemplateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL) from exc
    return _to_response(template)


@router.post("/templates/{template_id}/duplicate", status_code=201)
async def duplicate_template(
    template_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> TemplateResponse:
    service = TemplateService(session=session, tenant_id=current_user.tenant_id)
    try:
        template = await service.duplicate(template_id, current_user.id)
    except TemplateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL) from exc
    return _to_response(template)
