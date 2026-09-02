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


def _has_active_lawsuit_clause(active: bool) -> ColumnElement[bool]:
    """Spec 101, regras 5-6. Importado aqui dentro do módulo (não do domínio de processos)
    porque a condição é sobre `customers` — quem consulta é a listagem de contatos.

    `is_client` NÃO entra: a regra 5 fala em "ser parte", e parte contrária de um processo
    em curso também é um contato com processo ativo.
    """
    from app.domain.lawsuits.models import Lawsuit, LawsuitParty

    exists = (
        select(literal(1))
        .select_from(LawsuitParty)
        .join(Lawsuit, Lawsuit.id == LawsuitParty.lawsuit_id)
        .where(LawsuitParty.customer_id == Customer.id, Lawsuit.is_archived.is_(False))
        .exists()
    )
    return exists if active else ~exists


def _filtros_simples(
    *,
    person_type: PersonType | None,
    state: str | None,
    city: str | None,
    origin_id: uuid.UUID | None,
) -> list[ColumnElement[bool]]:
    """Igualdade direta. Estado e cidade comparam em minúsculas dos DOIS lados — o
    usuário digita "sp" ou "SP" e as duas coisas têm que achar o mesmo contato."""
    condicoes: list[ColumnElement[bool]] = []
    if person_type is not None:
        condicoes.append(Customer.type == person_type)
    for valor, coluna in ((state, Customer.state), (city, Customer.city)):
        if valor:
            condicoes.append(func.lower(coluna) == valor.lower())
    if origin_id is not None:
        condicoes.append(Customer.origin_id == origin_id)
    return condicoes


def _busca_por_nome_ou_documento(query: str) -> ColumnElement[bool]:
    """Regra 1: nome é busca parcial sem acento; CPF/CNPJ é exato.

    Um filtro só — se `query` não tiver dígitos, a comparação de `identification` nunca
    bate (ele só guarda dígitos), então não é preciso "detectar" a intenção de quem
    digitou.
    """
    search_pattern = func.concat("%", func.unaccent(func.lower(literal(query))), "%")
    return or_(
        func.unaccent(func.lower(Customer.name)).ilike(search_pattern),
        Customer.identification == strip_document_mask(query),
    )


def _filtro_de_aniversario(birthdays: str | None, today: date) -> list[ColumnElement[bool]]:
    """Regra 6: aniversário ignora o ano — compara mês, e no escopo do dia também o dia."""
    if birthdays not in ("day", "month"):
        return []
    condicoes = [func.date_part("month", Customer.birthdate) == today.month]
    if birthdays == "day":
        condicoes.append(func.date_part("day", Customer.birthdate) == today.day)
    return condicoes


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
        today: date,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = [Customer.is_archived.is_(archived)]

        if query:
            filters.append(_busca_por_nome_ou_documento(query))
        filters += _filtros_simples(
            person_type=person_type, state=state, city=city, origin_id=origin_id
        )
        filters += datetime_range(Customer.created_at, created_from, created_to)
        if has_active_lawsuit is not None:
            # Spec 101, regra 5: "processo ativo" é ser parte (`lawsuit_parties`) de ao
            # menos um processo não arquivado. EXISTS correlacionado, não JOIN — um
            # contato com três processos ativos não pode aparecer três vezes na listagem.
            filters.append(_has_active_lawsuit_clause(has_active_lawsuit))
        filters += _filtro_de_aniversario(birthdays, today)
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
        # Sem default (spec 114): o filtro de aniversário depende do dia do escritório, e
        # um default aqui devolveria silenciosamente o dia do servidor.
        today: date,
        sort: str = "created_at",
        descending: bool = True,
        cursor: tuple[str, uuid.UUID] | None = None,
        limit: int = 20,
    ) -> tuple[Sequence[Customer], int]:
        """Listagem paginada (CLAUDE.md §6) — keyset, nunca offset (regra 10)."""
        filters = self._build_filters(
            today=today,
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

    async def get_birthdays(self, *, scope: str, today: date) -> Sequence[Customer]:
        """Regra 6: aniversariantes ignoram o ano (compara mês e dia).

        `today` vem do escritório (spec 114): "quem faz aniversário hoje" é a pergunta
        que mais depende do fuso — de madrugada, o servidor já está no dia seguinte e a
        lista sai com os aniversariantes errados.
        """
        filters: list[ColumnElement[bool]] = [
            Customer.is_archived.is_(False),
            Customer.birthdate.is_not(None),
        ]
        filters.append(func.date_part("month", Customer.birthdate) == today.month)
        if scope == "day":
            filters.append(func.date_part("day", Customer.birthdate) == today.day)
        stmt = select(Customer).where(*filters).order_by(Customer.name)
        return (await self.session.scalars(stmt)).all()

    async def dashboard_counts(
        self, *, this_month: tuple[date, date], last_month: tuple[date, date]
    ) -> tuple[int, int, int, int]:
        """Os contadores do dashboard numa varredura só (spec 098, regra 1).

        Eram três `SELECT count(*)` sobre a MESMA tabela, com a mesma cláusula de RLS,
        diferindo só no predicado — três planos, três varreduras. `count(*) FILTER
        (WHERE ...)` calcula os três num passe. É a diferença entre 7 e 5 queries no
        dashboard de contatos, e num escritório com 100 mil contatos é a diferença
        entre três varreduras e uma.

        Spec 101, regra 6: `with_active_lawsuit` entra como QUARTO filtro da mesma
        varredura, não como query nova — o orçamento de queries do endpoint (§11 do
        CLAUDE.md) não muda por causa dele. `without_active_lawsuit` é derivado no
        serviço (`total - with`), garantindo que os dois somem `total` por construção.
        """
        stmt = select(
            func.count().filter(Customer.is_archived.is_(False)),
            func.count().filter(*datetime_range(Customer.created_at, *this_month)),
            func.count().filter(*datetime_range(Customer.created_at, *last_month)),
            func.count().filter(Customer.is_archived.is_(False), _has_active_lawsuit_clause(True)),
        ).select_from(Customer)
        row = (await self.session.execute(stmt)).one()
        return int(row[0]), int(row[1]), int(row[2]), int(row[3])

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
