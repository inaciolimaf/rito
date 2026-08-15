from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_file_storage
from app.core.image_processing import InvalidImageError
from app.core.permissions import UserRole, require_role
from app.domain.account.exceptions import AccountNotFoundError, ResponsibleUserNotFoundError
from app.domain.account.models import Account
from app.domain.account.schemas import (
    AccessTrackingResponse,
    AccessTrackingUpdateRequest,
    AccountPlanUpdateRequest,
    AccountResponse,
    AccountUpdateRequest,
    PublicationsSettingsResponse,
    PublicationsSettingsUpdateRequest,
)
from app.domain.account.service import AccountService
from app.domain.auth.deps import get_session_for_current_user
from app.domain.users.models import User
from app.integrations.storage.base import FileStorage

router = APIRouter(prefix="/account", tags=["account"])


def _to_response(account: Account, storage: FileStorage) -> AccountResponse:
    return AccountResponse(
        id=account.id,
        name=account.name,
        alternate_name=account.alternate_name,
        identification=account.identification,
        country=account.country,
        state=account.state,
        city=account.city,
        postal_code=account.postal_code,
        street=account.street,
        region=account.region,
        cellphone=account.cellphone,
        phone=account.phone,
        email=str(account.email),
        email_admin=str(account.email_admin),
        site=account.site,
        timezone=account.timezone,
        logo_url=storage.public_url(account.logo_key) if account.logo_key else None,
        plan=account.plan,
        track_access_logs=account.track_access_logs,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


@router.get("")
async def get_account(
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> AccountResponse:
    service = AccountService(session=session, storage=storage, tenant_id=current_user.tenant_id)
    account = await service.get()
    if account is None:
        raise HTTPException(status_code=404, detail="Conta ainda não configurada.")
    return _to_response(account, storage)


@router.put("")
async def update_account(
    payload: AccountUpdateRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> AccountResponse:
    service = AccountService(session=session, storage=storage, tenant_id=current_user.tenant_id)
    account = await service.upsert(payload)
    return _to_response(account, storage)


@router.post("/logo")
async def upload_account_logo(
    file: UploadFile,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> AccountResponse:
    service = AccountService(session=session, storage=storage, tenant_id=current_user.tenant_id)
    content = await file.read()
    content_type = file.content_type or "application/octet-stream"
    try:
        account = await service.upload_logo(content, content_type)
    except InvalidImageError as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conta ainda não configurada.") from exc
    return _to_response(account, storage)


@router.put("/plan")
async def update_account_plan(
    payload: AccountPlanUpdateRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> AccountResponse:
    service = AccountService(session=session, storage=storage, tenant_id=current_user.tenant_id)
    try:
        account = await service.update_plan(payload.plan)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conta ainda não configurada.") from exc
    return _to_response(account, storage)


@router.get("/publications-settings")
async def get_publications_settings(
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> PublicationsSettingsResponse:
    service = AccountService(session=session, storage=storage, tenant_id=current_user.tenant_id)
    account = await service.get()
    if account is None:
        raise HTTPException(status_code=404, detail="Conta ainda não configurada.")
    return PublicationsSettingsResponse(
        default_publications_user_id=account.default_publications_user_id
    )


@router.put("/publications-settings")
async def update_publications_settings(
    payload: PublicationsSettingsUpdateRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> PublicationsSettingsResponse:
    service = AccountService(session=session, storage=storage, tenant_id=current_user.tenant_id)
    try:
        account = await service.update_publications_settings(payload.default_publications_user_id)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conta ainda não configurada.") from exc
    except ResponsibleUserNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Responsável não encontrado.") from exc
    return PublicationsSettingsResponse(
        default_publications_user_id=account.default_publications_user_id
    )


@router.put("/access-tracking")
async def update_access_tracking(
    payload: AccessTrackingUpdateRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> AccessTrackingResponse:
    """Spec 073 §5: liga/desliga o rastreamento. Regra 2 (aviso de transparência
    LGPD) é responsabilidade da UI — este endpoint só persiste a escolha."""
    service = AccountService(session=session, storage=storage, tenant_id=current_user.tenant_id)
    try:
        account = await service.update_access_tracking(payload.enabled)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conta ainda não configurada.") from exc
    return AccessTrackingResponse(track_access_logs=account.track_access_logs)
