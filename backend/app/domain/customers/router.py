import uuid
from collections.abc import Mapping
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock
from app.core.deps import get_file_storage, get_messaging_channels, get_redis
from app.core.http import get_or_404
from app.core.image_processing import InvalidImageError
from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_clock, get_session_for_current_user
from app.domain.customers.exceptions import CustomerIdentificationAlreadyExistsError
from app.domain.customers.models import Customer
from app.domain.customers.schemas import (
    BirthdayItemResponse,
    CheckDuplicateResponse,
    CustomerCreateRequest,
    CustomerExportRequest,
    CustomerFilters,
    CustomerListItemResponse,
    CustomerListResponse,
    CustomerResponse,
    CustomerStatsResponse,
    CustomerUpdateRequest,
    DuplicateCandidateResponse,
    MaritalStatusResponse,
)
from app.domain.customers.service import CustomerService, MaritalStatusService
from app.domain.notifications.dispatch import NotificationDispatcher
from app.domain.notifications.models import NotificationEvent
from app.domain.users.models import User
from app.integrations.messaging.base import MessagingChannel
from app.integrations.storage.base import FileStorage

_DEFAULT_PAGE_SIZE = 20

customers_router = APIRouter(prefix="/customers", tags=["customers"])
marital_statuses_router = APIRouter(prefix="/marital-statuses", tags=["marital-statuses"])


def _customer_to_response(customer: Customer, storage: FileStorage) -> CustomerResponse:
    return CustomerResponse(
        id=customer.id,
        type=customer.type,
        name=customer.name,
        identification=customer.identification,
        document=customer.document,
        origin_id=customer.origin_id,
        notes=customer.notes,
        birthdate=customer.birthdate,
        marital_status_id=customer.marital_status_id,
        occupation=customer.occupation,
        gender=customer.gender,
        nationality=customer.nationality,
        mother_name=customer.mother_name,
        cellphone=customer.cellphone,
        phone=customer.phone,
        email=customer.email,
        country=customer.country,
        postal_code=customer.postal_code,
        state=customer.state,
        city=customer.city,
        street=customer.street,
        region=customer.region,
        number_pis=customer.number_pis,
        number_ctps=customer.number_ctps,
        number_cid=customer.number_cid,
        photo_url=storage.public_url(customer.photo_key) if customer.photo_key else None,
        has_representative=customer.has_representative,
        rep_name=customer.rep_name,
        rep_identification=customer.rep_identification,
        rep_document=customer.rep_document,
        rep_birthdate=customer.rep_birthdate,
        rep_country=customer.rep_country,
        rep_state=customer.rep_state,
        rep_city=customer.rep_city,
        rep_street=customer.rep_street,
        rep_region=customer.rep_region,
        rep_postal_code=customer.rep_postal_code,
        is_archived=customer.is_archived,
        created_at=customer.created_at,
        updated_at=customer.updated_at,
    )


@customers_router.post("", status_code=201)
async def create_customer(
    payload: CustomerCreateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    redis: Redis = Depends(get_redis),
    storage: FileStorage = Depends(get_file_storage),
    channels: Mapping[str, MessagingChannel] = Depends(get_messaging_channels),
) -> CustomerResponse:
    # Spec 098, regra 9: a escrita derruba o cache do dashboard.
    service = CustomerService(session=session, tenant_id=current_user.tenant_id, cache=redis)
    try:
        customer = await service.create(payload)
    except CustomerIdentificationAlreadyExistsError as exc:
        raise HTTPException(
            status_code=409, detail="Já existe um contato com esse CPF/CNPJ."
        ) from exc
    dispatcher = NotificationDispatcher(
        session=session, tenant_id=current_user.tenant_id, channels=channels
    )
    await dispatcher.dispatch(
        NotificationEvent.NOVO_CLIENTE,
        title="Novo contato cadastrado",
        body=customer.name,
        link="/customers",
    )
    return _customer_to_response(customer, storage)


def _item_to_response(customer: Customer) -> CustomerListItemResponse:
    whatsapp_link = f"https://wa.me/55{customer.cellphone}" if customer.cellphone else None
    return CustomerListItemResponse(
        id=customer.id,
        type=customer.type,
        name=customer.name,
        cellphone=customer.cellphone,
        whatsapp_link=whatsapp_link,
        city=customer.city,
        birthdate=customer.birthdate,
        is_archived=customer.is_archived,
        created_at=customer.created_at,
    )


@customers_router.get("")
async def list_customers(
    # Os dez filtros chegam como um objeto só (spec 116). O FastAPI expande os campos do
    # modelo em query params com os MESMOS nomes, tipos e defaults — o `CustomerFilters`
    # já era construído logo abaixo, campo a campo; agora ele é construído na porta.
    filters: CustomerFilters = Depends(),
    sort: Literal["name", "created_at"] = Query(default="created_at"),
    order: Literal["asc", "desc"] = Query(default="desc"),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=100),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    clock: Clock = Depends(get_clock),
) -> CustomerListResponse:
    service = CustomerService(session=session, tenant_id=current_user.tenant_id)
    items, next_cursor, total = await service.list_customers(
        today=clock.today(), filters=filters, sort=sort, order=order, cursor=cursor, limit=limit
    )
    return CustomerListResponse(
        items=[_item_to_response(item) for item in items], next_cursor=next_cursor, total=total
    )


@customers_router.get("/stats")
async def get_customer_stats(
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    redis: Redis = Depends(get_redis),
    clock: Clock = Depends(get_clock),
) -> CustomerStatsResponse:
    service = CustomerService(session=session, tenant_id=current_user.tenant_id, cache=redis)
    return await service.get_stats(clock.today())


@customers_router.get("/birthdays")
async def get_customer_birthdays(
    scope: Literal["day", "month"] = Query(...),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    clock: Clock = Depends(get_clock),
) -> list[BirthdayItemResponse]:
    service = CustomerService(session=session, tenant_id=current_user.tenant_id)
    customers = await service.get_birthdays(today=clock.today(), scope=scope)
    return [
        BirthdayItemResponse(id=c.id, name=c.name, birthdate=c.birthdate)
        for c in customers
        if c.birthdate is not None
    ]


@customers_router.post("/export")
async def export_customers(
    payload: CustomerExportRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    clock: Clock = Depends(get_clock),
) -> Response:
    service = CustomerService(session=session, tenant_id=current_user.tenant_id)
    content = await service.export(
        today=clock.today(), format_=payload.format, filters=payload.filters
    )
    media_type = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if payload.format == "xlsx"
        else "application/pdf"
    )
    filename = f"contatos.{payload.format}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@customers_router.get("/check-duplicate")
async def check_duplicate_customer(
    name: str = Query(...),
    birthdate: date = Query(...),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> CheckDuplicateResponse:
    """Regra 9 — registrado antes de `/{customer_id}` para não ser interpretado como um
    id (`check-duplicate` não é um UUID válido, mas a ordem de registro do FastAPI importa
    quando um path literal e um path parametrizado convivem no mesmo prefixo)."""
    service = CustomerService(session=session, tenant_id=current_user.tenant_id)
    candidates = await service.find_duplicates(name=name, birthdate=birthdate)
    return CheckDuplicateResponse(
        has_duplicate=len(candidates) > 0,
        candidates=[
            DuplicateCandidateResponse(id=candidate.id, name=candidate.name)
            for candidate in candidates
        ],
    )


@customers_router.get("/{customer_id}")
async def get_customer(
    customer_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> CustomerResponse:
    service = CustomerService(session=session, tenant_id=current_user.tenant_id)
    customer = await get_or_404(lambda: service.get(customer_id), "Contato não encontrado.")
    return _customer_to_response(customer, storage)


@customers_router.put("/{customer_id}")
async def update_customer(
    customer_id: uuid.UUID,
    payload: CustomerUpdateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    redis: Redis = Depends(get_redis),
    storage: FileStorage = Depends(get_file_storage),
) -> CustomerResponse:
    # Spec 098, regra 9: a escrita derruba o cache do dashboard.
    service = CustomerService(session=session, tenant_id=current_user.tenant_id, cache=redis)
    customer = await get_or_404(lambda: service.get(customer_id), "Contato não encontrado.")

    try:
        updated = await service.update(customer, payload)
    except CustomerIdentificationAlreadyExistsError as exc:
        raise HTTPException(
            status_code=409, detail="Já existe um contato com esse CPF/CNPJ."
        ) from exc
    return _customer_to_response(updated, storage)


@customers_router.delete("/{customer_id}", status_code=204)
async def archive_customer(
    customer_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    redis: Redis = Depends(get_redis),
) -> None:
    # Spec 098, regra 9: a escrita derruba o cache do dashboard.
    service = CustomerService(session=session, tenant_id=current_user.tenant_id, cache=redis)
    customer = await get_or_404(lambda: service.get(customer_id), "Contato não encontrado.")
    await service.archive(customer)


@customers_router.post("/{customer_id}/photo")
async def upload_customer_photo(
    customer_id: uuid.UUID,
    file: UploadFile,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> CustomerResponse:
    service = CustomerService(session=session, tenant_id=current_user.tenant_id)
    customer = await get_or_404(lambda: service.get(customer_id), "Contato não encontrado.")

    content = await file.read()
    content_type = file.content_type or "application/octet-stream"
    try:
        updated = await service.upload_photo(customer, content, content_type, storage)
    except InvalidImageError as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc
    return _customer_to_response(updated, storage)


@marital_statuses_router.get("")
async def list_marital_statuses(
    _current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> list[MaritalStatusResponse]:
    statuses = await MaritalStatusService(session).list_all()
    return [MaritalStatusResponse(id=item.id, name=item.name) for item in statuses]
