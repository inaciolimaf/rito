import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

from sqlalchemy import (
    Case,
    ColumnElement,
    CompoundSelect,
    Row,
    case,
    func,
    literal,
    or_,
    select,
    union_all,
)
from sqlalchemy.orm import InstrumentedAttribute

from app.core.br_documents import strip_document_mask
from app.core.listing import Page, datetime_range, paginate_keyset, unaccented_contains
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

# Discriminadores do `UNION ALL` de `dimension_counts`. Constantes, e não strings soltas
# nas três pernas da união: um erro de digitação aqui devolveria uma dimensão vazia sem
# erro nenhum, que é a falha mais cara de diagnosticar.
_ORIGIN = "origin"
_OCCUPATION = "occupation"
_AGE = "age"


@dataclass(frozen=True, slots=True)
class DimensionCounts:
    """As três distribuições do painel de contatos, já ordenadas como a tela as mostra."""

    origins: list[tuple[str, int]]
    occupations: list[tuple[str, int]]
    age_ranges: list[tuple[str, int]]


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


def _equality_filters(
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


def _search_by_name_or_document(query: str) -> ColumnElement[bool]:
    """Regra 1: nome é busca parcial sem acento; CPF/CNPJ é exato.

    Um filtro só — se `query` não tiver dígitos, a comparação de `identification` nunca
    bate (ele só guarda dígitos), então não é preciso "detectar" a intenção de quem
    digitou.

    Spec 137: o lado do nome era uma quarta cópia do predicado de `unaccented_contains`
    — e a única que precisava casar com um índice. Agora chama a função, e a expressão
    passou a ser exatamente a do `ix_customers_name_trgm` reconstruído na migration 137.
    """
    return or_(
        unaccented_contains(Customer.name, query),
        Customer.identification == strip_document_mask(query),
    )


# O escopo do filtro de aniversário. Alias, e não `str`, porque a dívida 34 nasceu
# exatamente de um `str` aceitar um valor que ninguém implementou.
BirthdayScope = Literal["day", "month"]


def _birthday_filter(
    birthdays: BirthdayScope | None, month: int | None, today: date
) -> list[ColumnElement[bool]]:
    """Regra 6: aniversário ignora o ANO — compara mês, e no escopo do dia também o dia.

    `month` só vale no escopo `month`, e serve à rota pública, que deixa o integrador pedir
    um mês qualquer («quem faz aniversário em dezembro?») sem esperar dezembro chegar. No
    escopo `day` ele é ignorado de propósito: «aniversariantes de hoje» é uma data completa,
    e aceitar um mês diferente do de hoje devolveria lista sempre vazia.

    Sem `month`, o mês é o de `today` — que já chega no fuso do escritório (spec 114).
    """
    if birthdays is None:
        return []
    alvo = today.month if birthdays == "day" else (month or today.month)
    condicoes = [func.date_part("month", Customer.birthdate) == alvo]
    if birthdays == "day":
        condicoes.append(func.date_part("day", Customer.birthdate) == today.day)
    return condicoes


@dataclass(frozen=True, slots=True)
class CustomerQuery:
    """Os filtros de listagem de contatos, do jeito que o REPOSITÓRIO os entende.

    Não é o `CustomerFilters` de `schemas.py`, e a diferença não é acidental: aquele é o
    contrato HTTP (nomes de query param, validação de entrada) e este é a linguagem do
    domínio. Os nomes divergem porque a API fala `q` e `type`, e uma query fala `query` e
    `person_type`.

    `birthdays` foi a divergência que importava, e a **dívida 34** morava nela: a rota pública
    mandava `"month:<n>"`, o filtro só reconhecia `"day"` e `"month"`, e a rota respondia os
    primeiros mil contatos do escritório em vez dos aniversariantes. A spec 116 tornou o tipo
    honesto sobre o descasamento; a 124 o eliminou, separando o ESCOPO (`birthdays`) do
    PARÂMETRO (`birthday_month`) em dois campos tipados. Um valor que o schema não conseguia
    expressar deixou de existir.
    """

    query: str | None = None
    person_type: PersonType | None = None
    state: str | None = None
    city: str | None = None
    origin_id: uuid.UUID | None = None
    created_from: date | None = None
    created_to: date | None = None
    has_active_lawsuit: bool | None = None
    birthdays: BirthdayScope | None = None
    birthday_month: int | None = None
    archived: bool = False


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

    def _build_filters(self, q: CustomerQuery, today: date) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = [Customer.is_archived.is_(q.archived)]

        if q.query:
            filters.append(_search_by_name_or_document(q.query))
        filters += _equality_filters(
            person_type=q.person_type, state=q.state, city=q.city, origin_id=q.origin_id
        )
        filters += datetime_range(Customer.created_at, q.created_from, q.created_to)
        if q.has_active_lawsuit is not None:
            # Spec 101, regra 5: "processo ativo" é ser parte (`lawsuit_parties`) de ao
            # menos um processo não arquivado. EXISTS correlacionado, não JOIN — um
            # contato com três processos ativos não pode aparecer três vezes na listagem.
            filters.append(_has_active_lawsuit_clause(q.has_active_lawsuit))
        filters += _birthday_filter(q.birthdays, q.birthday_month, today)
        return filters

    async def list_filtered(
        self,
        *,
        filters: CustomerQuery = CustomerQuery(),
        page: Page = Page(),
        # Sem default (spec 114): o filtro de aniversário depende do dia do escritório, e
        # um default aqui devolveria silenciosamente o dia do servidor.
        today: date,
    ) -> tuple[Sequence[Customer], int]:
        """Listagem paginada (CLAUDE.md §6) — keyset, nunca offset (regra 10)."""
        condicoes = self._build_filters(filters, today)

        count_stmt = select(func.count()).select_from(Customer)
        for condition in condicoes:
            count_stmt = count_stmt.where(condition)
        total = (await self.session.execute(count_stmt)).scalar_one()

        sort_column: InstrumentedAttribute[str] | InstrumentedAttribute[datetime] = (
            Customer.name if page.sort == "name" else Customer.created_at
        )
        stmt = select(Customer)
        for condition in condicoes:
            stmt = stmt.where(condition)
        stmt = paginate_keyset(
            stmt,
            sort_column=sort_column,
            id_column=Customer.id,
            descending=page.descending,
            cursor=page.cursor,
            limit=page.limit,
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
    ) -> tuple[int, int, int]:
        """Os contadores do dashboard numa varredura só (spec 098, regra 1).

        Eram três `SELECT count(*)` sobre a MESMA tabela, com a mesma cláusula de RLS,
        diferindo só no predicado — três planos, três varreduras. `count(*) FILTER
        (WHERE ...)` calcula os três num passe. É a diferença entre 7 e 5 queries no
        dashboard de contatos, e num escritório com 100 mil contatos é a diferença
        entre três varreduras e uma.

        Spec 137: `with_active_lawsuit` SAIU daqui. Ele era o quarto filtro desta
        varredura (spec 101, regra 6) e, junto com os outros três, ia para o cache de 5
        minutos de `customers:stats` — que só cai quando alguém escreve um CONTATO. Um
        processo novo mudava o número e não derrubava nada, e o painel mostrava zero
        contato com processo ativo pelo tempo do TTL. Ver `active_lawsuit_customers`.
        """
        stmt = select(
            func.count().filter(Customer.is_archived.is_(False)),
            func.count().filter(*datetime_range(Customer.created_at, *this_month)),
            func.count().filter(*datetime_range(Customer.created_at, *last_month)),
        ).select_from(Customer)
        row = (await self.session.execute(stmt)).one()
        return int(row[0]), int(row[1]), int(row[2])

    async def active_lawsuit_customers(self) -> int:
        """Contatos não arquivados que são parte de ao menos um processo em curso.

        Consulta própria, e de propósito FORA do cache (spec 137): é o único número do
        painel de contatos que muda por escrita de PROCESSO, e nenhum caminho de escrita
        de processo passa por `CustomerService`. Cachear por evento aqui exigiria que
        toda futura escrita de processo se lembrasse de derrubar uma chave de outro
        domínio — a lista que ninguém mantém.

        A conta é a mesma da regra 5 da spec 101 ("ser parte de processo não arquivado"),
        virada do avesso: em vez de um `EXISTS` correlacionado por contato (que percorre
        os 100 mil), conta clientes DISTINTOS a partir de `lawsuit_parties`, que é a
        tabela pequena. Medido em 100 mil contatos / 20 mil processos: 413 ms no
        `EXISTS` contra 39 ms aqui.
        """
        from app.domain.lawsuits.models import Lawsuit, LawsuitParty

        stmt = (
            select(func.count(func.distinct(LawsuitParty.customer_id)))
            .select_from(LawsuitParty)
            .join(Lawsuit, Lawsuit.id == LawsuitParty.lawsuit_id)
            .join(Customer, Customer.id == LawsuitParty.customer_id)
            .where(Lawsuit.is_archived.is_(False), Customer.is_archived.is_(False))
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def dimension_counts(self, limit: int = _TOP_N) -> DimensionCounts:
        """Origem, ocupação e faixa etária num único statement (spec 137).

        Eram três `GROUP BY` sobre `customers WHERE NOT is_archived`, cada um num
        round-trip. São agregações diferentes sobre o mesmo recorte, e `UNION ALL` com
        uma coluna discriminadora as junta sem misturar: o Postgres ainda faz três
        agregações, mas o cliente paga uma ida ao banco em vez de três.

        Isso não é maquiagem de gate — é o que abriu espaço no orçamento do §11 para
        `active_lawsuit_customers` entrar como consulta sempre fresca sem estourar as 5
        queries de `/api/v1/customers/stats` (medido: 5 antes, 4 depois).
        """
        nao_arquivado = Customer.is_archived.is_(False)
        origens = (
            select(
                literal(_ORIGIN).label("dimension"),
                CustomerOrigin.name.label("label"),
                func.count(Customer.id).label("total"),
            )
            .select_from(Customer)
            .join(CustomerOrigin, CustomerOrigin.id == Customer.origin_id)
            .where(nao_arquivado)
            .group_by(CustomerOrigin.name)
        )
        ocupacoes = (
            select(
                literal(_OCCUPATION),
                Customer.occupation,
                func.count(Customer.id),
            )
            .where(nao_arquivado, Customer.occupation.is_not(None))
            .group_by(Customer.occupation)
        )
        bucket = _age_bucket_expression()
        faixas = (
            select(literal(_AGE), bucket, func.count(Customer.id))
            .where(nao_arquivado)
            .group_by(bucket)
        )
        uniao: CompoundSelect[Any] = union_all(origens, ocupacoes, faixas)
        linhas: Sequence[Row[Any]] = (await self.session.execute(uniao)).all()
        return _split_dimensions(linhas, limit)


def _top_n_with_others(rows: Sequence[tuple[str, int]], limit: int) -> list[tuple[str, int]]:
    """Regra 5: top N e agrupa o resto em "Outros"."""
    top = list(rows[:limit])
    rest = sum(count for _name, count in rows[limit:])
    if rest > 0:
        top.append(("Outros", rest))
    return top


def _by_dimension(linhas: Sequence[Row[Any]], dimensao: str) -> list[tuple[str, int]]:
    """As linhas de uma dimensão, do maior para o menor, sem rótulo nulo.

    A ordenação vive aqui e não no `ORDER BY`: uma união de três agregações só poderia
    ordenar o conjunto todo, e cada dimensão tem a sua ordem (as duas primeiras por
    contagem, a faixa etária pela idade)."""
    pares = (
        (rotulo, int(total))
        for dimension, rotulo, total in linhas
        if dimension == dimensao and rotulo
    )
    return sorted(pares, key=lambda par: par[1], reverse=True)


def _split_dimensions(linhas: Sequence[Row[Any]], limit: int) -> DimensionCounts:
    """Separa o resultado do `UNION ALL` nas três listas, cada uma com a regra que já
    valia quando eram três consultas: top N + "Outros" para origem e ocupação, ordem
    fixa das faixas para idade (regra 4)."""
    faixas = dict(_by_dimension(linhas, _AGE))
    rotulos = [rotulo for rotulo, _low, _high in _AGE_RANGES] + ["Não informado"]
    return DimensionCounts(
        origins=_top_n_with_others(_by_dimension(linhas, _ORIGIN), limit),
        occupations=_top_n_with_others(_by_dimension(linhas, _OCCUPATION), limit),
        age_ranges=[(rotulo, faixas[rotulo]) for rotulo in rotulos if faixas.get(rotulo)],
    )
