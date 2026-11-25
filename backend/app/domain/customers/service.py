import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import Cache, cached_json, invalidate, tenant_key
from app.core.image_processing import extension_for, process_image
from app.core.listing import Page
from app.core.repository import decode_cursor, encode_cursor
from app.domain.customers.exceptions import CustomerIdentificationAlreadyExistsError
from app.domain.customers.export import build_pdf, build_xlsx
from app.domain.customers.models import Customer, MaritalStatus, PersonType
from app.domain.customers.repository import (
    CustomerQuery,
    CustomerRepository,
    MaritalStatusRepository,
)
from app.domain.customers.schemas import (
    CustomerCreateRequest,
    CustomerFilters,
    CustomerStatsResponse,
    CustomerUpdateRequest,
)
from app.integrations.storage.base import FileStorage

_EXPORT_ROW_CAP = 50_000

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


def stats_cache_key(tenant_id: uuid.UUID) -> str:
    return tenant_key("customers:stats", tenant_id)


def _item(par: tuple[str, int]) -> dict[str, object]:
    """Um par (rótulo, contagem) na forma que `CountedItem` valida — e que sobrevive à
    ida e volta pelo JSON do cache, que é por onde este dicionário passa."""
    nome, contagem = par
    return {"name": nome, "count": contagem}


class MaritalStatusService:
    """Tabela de referência de estado civil. Sem `tenant_id` de propósito: a lista é
    global (o RLS não a cobre porque não há o que isolar). Existe para o router não
    falar com o repositório (spec 118, checagem 2)."""

    def __init__(self, session: AsyncSession) -> None:
        self.statuses = MaritalStatusRepository(session)

    async def list_all(self) -> list[MaritalStatus]:
        return list(await self.statuses.list_all())


def _variation(this_month: int, last_month: int) -> float:
    """Variação percentual do mês contra o anterior, sem divisão por zero.

    Sem base, `100%` quando entrou alguém e `0%` quando não entrou — e não «infinito» nem
    `None`. É a leitura que o usuário faz de qualquer jeito ao ver o card: partir de zero e
    ganhar contatos é crescimento total; partir de zero e continuar em zero não é variação.
    """
    if last_month > 0:
        return (this_month - last_month) / last_month * 100
    return 100.0 if this_month > 0 else 0.0


class CustomerService:
    def __init__(
        self, session: AsyncSession, tenant_id: uuid.UUID, *, cache: Cache | None = None
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.customers = CustomerRepository(session)
        # Spec 098, regra 9: o cache do dashboard. Opcional para o service continuar
        # utilizável sem Redis (worker, script, teste do cálculo puro).
        self.cache = cache

    async def get(self, customer_id: uuid.UUID) -> Customer | None:
        return await self.customers.get_by_id(customer_id)

    async def find_duplicates(self, *, name: str, birthdate: date) -> list[Customer]:
        return list(await self.customers.find_duplicates(name=name, birthdate=birthdate))

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
        criado = await self.customers.create(customer)
        await self._invalidate_stats()
        return criado

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
        await self._invalidate_stats()
        return customer

    async def archive(self, customer: Customer) -> None:
        # Regra 5: exclusão é soft — contato com processo vinculado nunca é apagado de fato.
        customer.is_archived = True
        await self._invalidate_stats()

    async def _invalidate_stats(self) -> None:
        """Regra 9: o evento derruba o cache; o TTL é só o teto do erro.

        Sem isto, cadastrar um contato e voltar ao dashboard mostraria o número velho
        por até cinco minutos — que o usuário lê como bug, não como cache.
        """
        await invalidate(self.cache, stats_cache_key(self.tenant_id))

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

    async def list_customers(
        self,
        *,
        filters: CustomerFilters,
        sort: str,
        order: Literal["asc", "desc"],
        cursor: str | None,
        limit: int,
        today: date,
    ) -> tuple[list[Customer], str | None, int]:
        decoded_cursor = decode_cursor(cursor) if cursor else None
        items, total = await self.customers.list_filtered(
            today=today,
            filters=_to_query(filters),
            page=Page(sort=sort, descending=order == "desc", cursor=decoded_cursor, limit=limit),
        )
        next_cursor = None
        if len(items) == limit:
            last = items[-1]
            last_sort_value = last.name if sort == "name" else last.created_at.isoformat()
            next_cursor = encode_cursor(last_sort_value, last.id)
        return list(items), next_cursor, total

    async def get_birthdays(self, *, scope: Literal["day", "month"], today: date) -> list[Customer]:
        return list(await self.customers.get_birthdays(scope=scope, today=today))

    async def get_stats(self, today: date) -> CustomerStatsResponse:
        """Dashboard de contatos com cache de 5 minutos (spec 098, regra 9).

        São cinco agregações sobre a base inteira de contatos; num escritório com 100 mil
        deles, calcular tudo a cada abertura da tela é trabalho jogado fora — os números
        mudam quando alguém cadastra alguém, não a cada segundo.

        A sexta saiu do cache na spec 137: `with_active_lawsuit` muda quando alguém
        escreve um PROCESSO, e escrita de processo nunca passou por aqui para derrubar a
        chave. Ficava em zero por até cinco minutos depois de o contato ganhar processo.
        """
        cacheado: dict[str, Any] = await cached_json(
            self.cache,
            stats_cache_key(self.tenant_id),
            # `cached_json` chama a função sem argumento; o dia do escritório entra
            # pelo fecho, não pela assinatura (spec 114).
            lambda: self._compute_stats(today),
            decode=dict,
        )
        # Spec 137: o único número do painel que muda por escrita de PROCESSO fica fora
        # do cache. Ver `CustomerRepository.active_lawsuit_customers`.
        with_active_lawsuit = await self.customers.active_lawsuit_customers()
        total = int(cacheado["total"])
        return CustomerStatsResponse(
            **cacheado,
            with_active_lawsuit=with_active_lawsuit,
            # Derivado, nunca contado de novo: regra 6 exige que os dois somem `total`.
            # O `max` existe porque as duas metades têm frescor diferente: `total` pode
            # vir do cache de 5 minutos e `with_active_lawsuit` é sempre de agora, então
            # um contato cadastrado e já vinculado a processo deixaria a subtração
            # negativa por alguns minutos. Zero é a resposta honesta nesse intervalo.
            without_active_lawsuit=max(total - with_active_lawsuit, 0),
        )

    async def _compute_stats(self, today: date) -> dict[str, Any]:
        this_month_start = today.replace(day=1)
        last_month_end = this_month_start - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)

        (
            total,
            this_month_count,
            last_month_count,
        ) = await self.customers.dashboard_counts(
            this_month=(this_month_start, today),
            last_month=(last_month_start, last_month_end),
        )
        variation = _variation(this_month_count, last_month_count)
        dimensoes = await self.customers.dimension_counts()

        return {
            "total": total,
            "variation_vs_last_month": round(variation, 2),
            "top_origins": [_item(par) for par in dimensoes.origins],
            "age_ranges": [_item(par) for par in dimensoes.age_ranges],
            "top_occupations": [_item(par) for par in dimensoes.occupations],
        }

    async def export(
        self, *, format_: Literal["xlsx", "pdf"], filters: CustomerFilters, today: date
    ) -> bytes:
        # Regra 7: respeita os filtros ativos, não a página visível; teto de 50.000 linhas.
        items, _total = await self.customers.list_filtered(
            today=today,
            filters=_to_query(filters),
            page=Page(limit=_EXPORT_ROW_CAP),
        )
        return build_xlsx(list(items)) if format_ == "xlsx" else build_pdf(list(items))


def _to_query(filters: CustomerFilters) -> CustomerQuery:
    """Traduz o filtro da API para a linguagem do repositório (spec 116).

    Os nomes divergem porque as duas camadas falam línguas diferentes — `q`/`type` são
    query params, `query`/`person_type` são critérios de consulta. A tradução vive aqui, no
    service, porque é ele quem faz a ponte entre HTTP e domínio (CLAUDE.md §5).
    """
    return CustomerQuery(
        query=filters.q,
        person_type=filters.type,
        state=filters.state,
        city=filters.city,
        origin_id=filters.origin_id,
        created_from=filters.created_from,
        created_to=filters.created_to,
        has_active_lawsuit=filters.has_active_lawsuit,
        birthdays=filters.birthdays,
        archived=filters.archived,
    )
