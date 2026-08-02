import uuid
from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import Case, ColumnElement, case, func, literal, or_, select
from sqlalchemy.orm import InstrumentedAttribute

from app.core.br_documents import strip_document_mask
from app.core.listing import datetime_range, paginate_keyset
from app.core.repository import BaseRepository
from app.domain.customer_origins.models import CustomerOrigin
from app.domain.customers.models import Customer, MaritalStatus, PersonType

_AGE_RANGES = [
    ("0-17", 0, 17),
    ("18-24", 18, 24),
    ("25-34", 25, 34),
    ("35-44", 35, 44),
    ("45-54", 45, 54),
    ("55-64", 55, 64),
    ("65+", 65, None),
]
_TOP_N = 10


def _age_bucket_expression() -> Case[str]:
    """Regra 4 (spec 019): faixas etárias fixas; sem nascimento vira "Não informado"."""
    age = func.date_part("year", func.age(func.current_date(), Customer.birthdate))
    whens: list[tuple[ColumnElement[bool], str]] = [
        (age.between(low, high) if high is not None else age >= low, label)
        for label, low, high in _AGE_RANGES
    ]
    return case(*whens, else_="Não informado")


class MaritalStatusRepository(BaseRepository[MaritalStatus]):
    model = MaritalStatus

    async def list_all(self) -> Sequence[MaritalStatus]:
        result = await self.session.scalars(select(MaritalStatus).order_by(MaritalStatus.id))
        return result.all()


class CustomerRepository(BaseRepository[Customer]):
    model = Customer

    async def get_by_identification(self, identification: str) -> Customer | None:
        result = await self.session.scalars(
            select(Customer).where(Customer.identification == identification)
        )
        return result.first()

    async def find_duplicates(self, *, name: str, birthdate: date) -> Sequence[Customer]:
        """Regra 9: mesmo nome (sem acento, case-insensitive) + mesmo nascimento."""
        result = await self.session.scalars(
            select(Customer).where(
                func.unaccent(func.lower(Customer.name)) == func.unaccent(func.lower(name)),
                Customer.birthdate == birthdate,
            )
        )
        return result.all()

    def _build_filters(
        self,
        *,
        query: str | None,
        person_type: PersonType | None,
        state: str | None,
        city: str | None,
        origin_id: uuid.UUID | None,
        created_from: date | None,
        created_to: date | None,
        has_active_lawsuit: bool | None,
        birthdays: str | None,
        archived: bool,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = [Customer.is_archived.is_(archived)]

        if query:
            # Regra 1: nome é busca parcial sem acento; CPF/CNPJ é exato. Um filtro só —
            # se `query` não tiver dígitos, a comparação de identification nunca bate
            # (identification só guarda dígitos), então não precisa "detectar" a intenção.
            digits = strip_document_mask(query)
            search_pattern = func.concat("%", func.unaccent(func.lower(literal(query))), "%")
            filters.append(
                or_(
                    func.unaccent(func.lower(Customer.name)).ilike(search_pattern),
                    Customer.identification == digits,
                )
            )
        if person_type is not None:
            filters.append(Customer.type == person_type)
        if state:
            filters.append(func.lower(Customer.state) == state.lower())
        if city:
            filters.append(func.lower(Customer.city) == city.lower())
        if origin_id is not None:
            filters.append(Customer.origin_id == origin_id)
        filters += datetime_range(Customer.created_at, created_from, created_to)
        if has_active_lawsuit:
            # Regra fora de alcance ainda: `lawsuits`/`lawsuit_customer` só chegam na spec
            # 022 (Descobertas) — nenhum contato tem processo ativo hoje, então pedir
            # has_active_lawsuit=true nunca encontra nada.
            filters.append(Customer.id == uuid.uuid4())
        if birthdays == "day":
            today = date.today()
            filters.append(func.date_part("month", Customer.birthdate) == today.month)
            filters.append(func.date_part("day", Customer.birthdate) == today.day)
        elif birthdays == "month":
            filters.append(func.date_part("month", Customer.birthdate) == date.today().month)

        return filters

    async def list_filtered(
        self,
        *,
        query: str | None = None,
        person_type: PersonType | None = None,
        state: str | None = None,
        city: str | None = None,
        origin_id: uuid.UUID | None = None,
        created_from: date | None = None,
        created_to: date | None = None,
        has_active_lawsuit: bool | None = None,
        birthdays: str | None = None,
        archived: bool = False,
        sort: str = "created_at",
        descending: bool = True,
        cursor: tuple[str, uuid.UUID] | None = None,
        limit: int = 20,
    ) -> tuple[Sequence[Customer], int]:
        """Listagem paginada (CLAUDE.md §6) — keyset, nunca offset (regra 10)."""
        filters = self._build_filters(
            query=query,
            person_type=person_type,
            state=state,
            city=city,
            origin_id=origin_id,
            created_from=created_from,
            created_to=created_to,
            has_active_lawsuit=has_active_lawsuit,
            birthdays=birthdays,
            archived=archived,
        )

        count_stmt = select(func.count()).select_from(Customer)
        for condition in filters:
            count_stmt = count_stmt.where(condition)
        total = (await self.session.execute(count_stmt)).scalar_one()

        sort_column: InstrumentedAttribute[str] | InstrumentedAttribute[datetime] = (
            Customer.name if sort == "name" else Customer.created_at
        )
        stmt = select(Customer)
        for condition in filters:
            stmt = stmt.where(condition)
        stmt = paginate_keyset(
            stmt,
            sort_column=sort_column,
            id_column=Customer.id,
            descending=descending,
            cursor=cursor,
            limit=limit,
        )

        items = (await self.session.scalars(stmt)).all()
        return items, total

    async def get_birthdays(self, *, scope: str) -> Sequence[Customer]:
        """Regra 6: aniversariantes ignoram o ano (compara mês e dia)."""
        today = date.today()
        filters: list[ColumnElement[bool]] = [
            Customer.is_archived.is_(False),
            Customer.birthdate.is_not(None),
        ]
        filters.append(func.date_part("month", Customer.birthdate) == today.month)
        if scope == "day":
            filters.append(func.date_part("day", Customer.birthdate) == today.day)
        stmt = select(Customer).where(*filters).order_by(Customer.name)
        return (await self.session.scalars(stmt)).all()

    async def count_active(self) -> int:
        return (
            await self.session.execute(
                select(func.count()).select_from(Customer).where(Customer.is_archived.is_(False))
            )
        ).scalar_one()

    async def count_created_between(self, start: date, end: date) -> int:
        return (
            await self.session.execute(
                select(func.count())
                .select_from(Customer)
                .where(*datetime_range(Customer.created_at, start, end))
            )
        ).scalar_one()

    async def top_origins(self, limit: int = _TOP_N) -> list[tuple[str, int]]:
        stmt = (
            select(CustomerOrigin.name, func.count(Customer.id))
            .select_from(Customer)
            .join(CustomerOrigin, CustomerOrigin.id == Customer.origin_id)
            .where(Customer.is_archived.is_(False))
            .group_by(CustomerOrigin.name)
            .order_by(func.count(Customer.id).desc())
        )
        rows = [(name, count) for name, count in (await self.session.execute(stmt)).all()]
        return _top_n_with_others(rows, limit)

    async def top_occupations(self, limit: int = _TOP_N) -> list[tuple[str, int]]:
        stmt = (
            select(Customer.occupation, func.count(Customer.id))
            .where(Customer.is_archived.is_(False), Customer.occupation.is_not(None))
            .group_by(Customer.occupation)
            .order_by(func.count(Customer.id).desc())
        )
        rows = [(name, count) for name, count in (await self.session.execute(stmt)).all() if name]
        return _top_n_with_others(rows, limit)

    async def age_ranges(self) -> list[tuple[str, int]]:
        bucket = _age_bucket_expression()
        stmt = (
            select(bucket, func.count(Customer.id))
            .where(Customer.is_archived.is_(False))
            .group_by(bucket)
        )
        counts: dict[str, int] = {
            label: count for label, count in (await self.session.execute(stmt)).all()
        }
        ordered_labels = [label for label, _low, _high in _AGE_RANGES] + ["Não informado"]
        return [(label, counts.get(label, 0)) for label in ordered_labels if counts.get(label, 0)]


def _top_n_with_others(rows: Sequence[tuple[str, int]], limit: int) -> list[tuple[str, int]]:
    """Regra 5: top N e agrupa o resto em "Outros"."""
    top = list(rows[:limit])
    rest = sum(count for _name, count in rows[limit:])
    if rest > 0:
        top.append(("Outros", rest))
    return top
