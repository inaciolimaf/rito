import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_file_storage, get_session, get_tenant_id
from app.core.http import get_or_404, parse_active_status
from app.core.image_processing import InvalidImageError
from app.core.permissions import FinancialAccess, UserRole, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.auth.exceptions import WeakPasswordError
from app.domain.users.exceptions import (
    CannotChangeOwnRoleError,
    EmailAlreadyRegisteredError,
    InvalidInvitationError,
    LastActiveGestorError,
    OabRequiredError,
)
from app.domain.users.models import User
from app.domain.users.repository import OccupationRepository
from app.domain.users.schemas import (
    AcceptInvitationRequest,
    InviteUserRequest,
    InviteUserResponse,
    MentionableUserResponse,
    OccupationResponse,
    PreferencesResponse,
    PreferencesUpdateRequest,
    UserListResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.domain.users.service import UserService
from app.integrations.storage.base import FileStorage

users_router = APIRouter(prefix="/users", tags=["users"])
occupations_router = APIRouter(prefix="/occupations", tags=["occupations"])
invitations_router = APIRouter(prefix="/invitations", tags=["invitations"])

_DEFAULT_PAGE_SIZE = 20


def _ensure_self_or_administrator(current_user: User, target_id: uuid.UUID) -> None:
    """ "Próprio usuário ou ADMINISTRADOR" (spec 012, seção 5) — GESTOR também passa,
    mesma hierarquia de `require_role` (GESTOR > ADMINISTRADOR, spec 005)."""
    if current_user.id == target_id:
        return
    if current_user.role in (UserRole.ADMINISTRADOR, UserRole.GESTOR):
        return
    raise HTTPException(status_code=403, detail="Sem permissão para acessar este usuário.")


def _to_user_response(user: User, *, requester: User, storage: FileStorage) -> UserResponse:
    # Regra 10: salário só é visível para quem tem financial_access >= READ_ONLY.
    can_see_salary = requester.financial_access != FinancialAccess.NONE
    return UserResponse(
        id=user.id,
        email=str(user.email),
        name=user.name,
        is_active=user.is_active,
        role=user.role,
        financial_access=user.financial_access,
        occupation_id=user.occupation_id,
        identification=user.identification,
        document=user.document,
        birthdate=user.birthdate,
        number_ctps=user.number_ctps,
        number_oab=user.number_oab,
        cellphone=user.cellphone,
        phone=user.phone,
        avatar_url=storage.public_url(user.avatar_key) if user.avatar_key else None,
        salary=user.salary if can_see_salary else None,
        admission_date=user.admission_date,
        resignation_date=user.resignation_date,
        work_start=user.work_start,
        work_interval=user.work_interval,
        work_end=user.work_end,
        points_goal=user.points_goal,
        report_deadline=user.report_deadline,
        report_deleted=user.report_deleted,
        is_responsible=user.is_responsible,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@users_router.get("")
async def list_users(
    role: UserRole | None = Query(default=None),
    status_: Literal["active", "inactive"] | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=100),
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> UserListResponse:
    service = UserService(session=session, tenant_id=current_user.tenant_id)
    items, next_cursor, total = await service.list_users(
        role=role, is_active=parse_active_status(status_), query=q, cursor=cursor, limit=limit
    )
    return UserListResponse(
        items=[_to_user_response(item, requester=current_user, storage=storage) for item in items],
        next_cursor=next_cursor,
        total=total,
    )


@users_router.post("/invite", status_code=201)
async def invite_user(
    payload: InviteUserRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> InviteUserResponse:
    service = UserService(session=session, tenant_id=current_user.tenant_id)
    try:
        invitation, _raw_token = await service.invite(actor=current_user, payload=payload)
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=409, detail="E-mail já cadastrado neste escritório."
        ) from exc
    # _raw_token: sem infra de e-mail ainda (mesma situação do forgot-password, spec 004) —
    # quem envia o convite de verdade obtém o token chamando o service direto, não pela API.
    return InviteUserResponse(
        id=invitation.id,
        email=str(invitation.email),
        role=invitation.role,
        expires_at=invitation.expires_at,
    )


@users_router.get("/me/preferences")
async def get_my_preferences(
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PreferencesResponse:
    service = UserService(session=session, tenant_id=current_user.tenant_id)
    user = await get_or_404(lambda: service.get(current_user.id), "Usuário não encontrado.")
    return PreferencesResponse(preferences=dict(user.preferences))


@users_router.put("/me/preferences")
async def put_my_preferences(
    payload: PreferencesUpdateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PreferencesResponse:
    service = UserService(session=session, tenant_id=current_user.tenant_id)
    user = await get_or_404(lambda: service.get(current_user.id), "Usuário não encontrado.")
    # Merge raso por chave (regra 7, spec 026): o cliente manda só o que quer mudar.
    user.preferences = {**user.preferences, **payload.preferences}
    return PreferencesResponse(preferences=dict(user.preferences))


@users_router.get("/mentionable")
async def list_mentionable_users(
    q: str | None = Query(default=None),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> list[MentionableUserResponse]:
    """Autocomplete de `@menção` (spec 035 §5): usuários ATIVOS do tenant, forma
    mínima (id + nome), aberto a qualquer colaborador — quem comenta precisa mencionar.
    Registrado antes de /{user_id} para não virar lookup por id."""
    service = UserService(session=session, tenant_id=current_user.tenant_id)
    users = await service.list_mentionable(query=q)
    return [MentionableUserResponse(id=user.id, name=user.name) for user in users]


@users_router.get("/{user_id}")
async def get_user(
    user_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> UserResponse:
    _ensure_self_or_administrator(current_user, user_id)
    service = UserService(session=session, tenant_id=current_user.tenant_id)
    user = await get_or_404(lambda: service.get(user_id), "Usuário não encontrado.")
    return _to_user_response(user, requester=current_user, storage=storage)


@users_router.put("/{user_id}")
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> UserResponse:
    _ensure_self_or_administrator(current_user, user_id)
    service = UserService(session=session, tenant_id=current_user.tenant_id)
    target = await get_or_404(lambda: service.get(user_id), "Usuário não encontrado.")

    try:
        updated = await service.update(actor=current_user, target=target, payload=payload)
    except CannotChangeOwnRoleError as exc:
        raise HTTPException(
            status_code=403, detail="Você não pode alterar o próprio perfil ou acesso financeiro."
        ) from exc
    except OabRequiredError as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc
    return _to_user_response(updated, requester=current_user, storage=storage)


@users_router.post("/{user_id}/deactivate", status_code=204)
async def deactivate_user(
    user_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> None:
    service = UserService(session=session, tenant_id=current_user.tenant_id)
    target = await get_or_404(lambda: service.get(user_id), "Usuário não encontrado.")

    try:
        await service.deactivate(target)
    except LastActiveGestorError as exc:
        raise HTTPException(
            status_code=409, detail="Não é possível inativar o último Gestor ativo."
        ) from exc


@users_router.post("/{user_id}/avatar")
async def upload_user_avatar(
    user_id: uuid.UUID,
    file: UploadFile,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> UserResponse:
    _ensure_self_or_administrator(current_user, user_id)
    service = UserService(session=session, tenant_id=current_user.tenant_id)
    target = await get_or_404(lambda: service.get(user_id), "Usuário não encontrado.")

    content = await file.read()
    content_type = file.content_type or "application/octet-stream"
    try:
        updated = await service.upload_avatar(target, content, content_type, storage)
    except InvalidImageError as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc
    return _to_user_response(updated, requester=current_user, storage=storage)


@occupations_router.get("")
async def list_occupations(
    _current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> list[OccupationResponse]:
    occupations = await OccupationRepository(session).list_all()
    return [OccupationResponse(id=item.id, name=item.name) for item in occupations]


@invitations_router.post("/accept", status_code=204)
async def accept_invitation(
    payload: AcceptInvitationRequest,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Público (com token) — mas ainda exige X-Tenant-Id, igual todo pré-auth desde a
    spec 004: RLS não deixa achar a linha certa sem saber o tenant antes da query."""
    service = UserService(session=session, tenant_id=tenant_id)
    try:
        await service.accept_invitation(payload)
    except InvalidInvitationError as exc:
        raise HTTPException(status_code=400, detail="Convite inválido ou expirado.") from exc
    except WeakPasswordError as exc:
        raise HTTPException(
            status_code=422, detail={"detail": "Senha não atende à política.", "errors": exc.errors}
        ) from exc
