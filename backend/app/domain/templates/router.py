import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.templates.exceptions import TemplateNotFoundError
from app.domain.templates.models import Template
from app.domain.templates.resolve import (
    CustomerScopeNotFoundError,
    LawsuitScopeNotFoundError,
    TemplateResolverService,
)
from app.domain.templates.schemas import (
    ResolvedTemplateResponse,
    ResolveTemplateRequest,
    TemplateCreateRequest,
    TemplateListResponse,
    TemplateResponse,
    TemplateUpdateRequest,
    VariableCatalogItem,
)
from app.domain.templates.service import TemplateService
from app.domain.templates.variables import VARIABLE_CATALOG
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
        header_content=template.header_content,
        footer_content=template.footer_content,
        watermark_text=template.watermark_text,
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
    template = await service.create(current_user.id, payload)
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
        template = await service.update(template_id, payload)
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


@router.get("/template-variables")
async def list_template_variables(
    _current_user: User = Depends(require_role(UserRole.COLABORADOR)),
) -> list[VariableCatalogItem]:
    return [
        VariableCatalogItem(namespace=namespace, key=key, label=label)
        for namespace, key, label in VARIABLE_CATALOG
    ]


@router.post("/templates/{template_id}/resolve")
async def resolve_template(
    template_id: uuid.UUID,
    payload: ResolveTemplateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> ResolvedTemplateResponse:
    service = TemplateResolverService(session=session, tenant_id=current_user.tenant_id)
    try:
        resolved = await service.resolve(
            template_id,
            customer_id=payload.customer_id,
            lawsuit_id=payload.lawsuit_id,
            current_user=current_user,
        )
    except TemplateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL) from exc
    except CustomerScopeNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Contato não encontrado.") from exc
    except LawsuitScopeNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Processo não encontrado.") from exc
    return ResolvedTemplateResponse(
        content=resolved.content,
        header_content=resolved.header_content,
        footer_content=resolved.footer_content,
        missing=resolved.missing,
    )


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
