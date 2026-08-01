import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.image_processing import extension_for, process_image
from app.domain.customers.exceptions import CustomerIdentificationAlreadyExistsError
from app.domain.customers.models import Customer, PersonType
from app.domain.customers.repository import CustomerRepository
from app.domain.customers.schemas import CustomerCreateRequest, CustomerUpdateRequest
from app.integrations.storage.base import FileStorage

_MAX_PHOTO_SIZE_BYTES = 5 * 1024 * 1024
_MAX_PHOTO_DIMENSION_PX = 400
_ALLOWED_PHOTO_CONTENT_TYPES = frozenset({"image/png", "image/jpeg"})

# Regra 2: alternar PF→PJ limpa os campos exclusivos de PF (seção 6 da spec).
_PF_ONLY_FIELDS = (
    "document",
    "birthdate",
    "marital_status_id",
    "occupation",
    "gender",
    "nationality",
    "mother_name",
    "number_pis",
    "number_ctps",
    "number_cid",
)


class CustomerService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.customers = CustomerRepository(session)

    async def get(self, customer_id: uuid.UUID) -> Customer | None:
        return await self.customers.get_by_id(customer_id)

    async def create(self, payload: CustomerCreateRequest) -> Customer:
        if payload.identification and (
            await self.customers.get_by_identification(payload.identification) is not None
        ):
            raise CustomerIdentificationAlreadyExistsError

        data = payload.model_dump()
        if payload.type == PersonType.PJ:
            for field in _PF_ONLY_FIELDS:
                data[field] = None

        customer = Customer(tenant_id=self.tenant_id, **data)
        return await self.customers.create(customer)

    async def update(self, customer: Customer, payload: CustomerUpdateRequest) -> Customer:
        if payload.identification and payload.identification != customer.identification:
            existing = await self.customers.get_by_identification(payload.identification)
            if existing is not None and existing.id != customer.id:
                raise CustomerIdentificationAlreadyExistsError

        data = payload.model_dump()
        if payload.type == PersonType.PJ:
            for field in _PF_ONLY_FIELDS:
                data[field] = None

        for field, value in data.items():
            setattr(customer, field, value)
        return customer

    async def archive(self, customer: Customer) -> None:
        # Regra 5: exclusão é soft — contato com processo vinculado nunca é apagado de fato.
        customer.is_archived = True

    async def upload_photo(
        self, customer: Customer, content: bytes, content_type: str, storage: FileStorage
    ) -> Customer:
        processed = process_image(
            content,
            content_type,
            max_size_bytes=_MAX_PHOTO_SIZE_BYTES,
            max_dimension_px=_MAX_PHOTO_DIMENSION_PX,
            allowed_content_types=_ALLOWED_PHOTO_CONTENT_TYPES,
            invalid_format_message="Formato inválido — use PNG ou JPG.",
        )
        extension = extension_for(content_type)
        key = f"customers/{self.tenant_id}/{customer.id}/{uuid.uuid4()}.{extension}"
        await storage.upload(key=key, content=processed, content_type=content_type)

        customer.photo_key = key
        customer.updated_at = datetime.now(UTC)
        return customer
