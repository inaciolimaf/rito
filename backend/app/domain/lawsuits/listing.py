"""Listagem de processos (spec 027): 12 visões rápidas + filtros combináveis.

Separado de `repository.py` (SRP): aqui só vive a query de listagem — a mais exigente do
módulo (partes agregadas sem N+1, último andamento correlacionado, keyset).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import ColumnElement, Row, Select, and_, func, literal, or_, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.selectable import ScalarSelect, Subquery

from app.core.listing import QuickViews, date_range, datetime_range, paginate_keyset
from app.domain.action_groups.models import ActionGroup, LawsuitType
from app.domain.customers.models import Customer
from app.domain.lawsuits.models import (
    ContingencyLevel,
    Lawsuit,
    LawsuitMovement,
    LawsuitParty,
)
from app.domain.lawsuits.schemas import LawsuitFiltersQuery
from app.domain.stages.models import Stage
from app.domain.users.models import User


def _idle(days: int) -> ColumnElement[bool]:
    # Regra 3: parado há N dias ou nunca movimentado.
    return or_(
        Lawsuit.last_movement_at.is_(None),
        Lawsuit.last_movement_at < func.now() - text(f"interval '{days} days'"),
    )


# As 12 visões rápidas (spec 027 §5) — atalho combinável com filtros (regra 1),
# declaradas no QuickViews da infra de listagem (spec 030).
LAWSUIT_VIEWS = QuickViews(
    default="all",
    views={
        "all": lambda: None,
        # Regra 2: ativo = não arquivado (visibilidade) E sem data de arquivamento (fato).
        "active": lambda: and_(Lawsuit.is_archived.is_(False), Lawsuit.archived_date.is_(None)),
        "moved_30d": lambda: Lawsuit.last_movement_at >= func.now() - text("interval '30 days'"),
        "moved_7d": lambda: Lawsuit.last_movement_at >= func.now() - text("interval '7 days'"),
        "moved_today": lambda: Lawsuit.last_movement_at >= func.date_trunc("day", func.now()),
        "never_captured": lambda: Lawsuit.last_movement_at.is_(None),
        "idle_30d": lambda: _idle(30),
        "idle_45d": lambda: _idle(45),
        "idle_90d": lambda: _idle(90),
        "closed_this_month": lambda: Lawsuit.closure_date
        >= func.date_trunc("month", func.current_date()),
        "filed_this_month": lambda: Lawsuit.process_date
        >= func.date_trunc("month", func.current_date()),
        "archived_this_month": lambda: Lawsuit.archived_date
        >= func.date_trunc("month", func.current_date()),
    },
)

EXPORT_ROW_LIMIT = 50_000  # regra 10


@dataclass
class LawsuitFilters:
    """Todos os filtros da listagem — combinam com AND (regra 8); os multivalorados
    (`*_ids`) combinam com OR entre si (IN)."""

    view: str = "all"
    q: str | None = None
    customer_id: uuid.UUID | None = None
    identification: str | None = None
    process_number: str | None = None
    protocol_number: str | None = None
    folder: str | None = None
    notes: str | None = None
    action_group_ids: list[uuid.UUID] = field(default_factory=list)
    lawsuit_type_ids: list[uuid.UUID] = field(default_factory=list)
    step_ids: list[int] = field(default_factory=list)
    stage_ids: list[uuid.UUID] = field(default_factory=list)
    court_ids: list[int] = field(default_factory=list)
    court_system_ids: list[int] = field(default_factory=list)
    user_ids: list[uuid.UUID] = field(default_factory=list)
    contingencies: list[ContingencyLevel] = field(default_factory=list)
    origin_ids: list[uuid.UUID] = field(default_factory=list)
    customer_type: str | None = None
    created_from: date | None = None
    created_to: date | None = None
    process_date_from: date | None = None
    process_date_to: date | None = None
    closure_from: date | None = None
    closure_to: date | None = None
    transit_from: date | None = None
    transit_to: date | None = None
    archived_from: date | None = None
    archived_to: date | None = None
    archived: bool | None = None
    display_stagnant: Literal["all", "stagnant", "active"] = "all"


@dataclass
class LawsuitListRow:
    lawsuit: Lawsuit
    lawsuit_type_name: str
    action_group_name: str
    stage_name: str
    parties: list[dict[str, object]]
    parties_total: int
    last_movement_title: str | None


BOARD_DEFAULT_LIMIT_PER_COLUMN = 50  # regra 7
BOARD_TOTAL_REFINE_THRESHOLD = 2_000  # regra 11: sugestão, nunca bloqueia


@dataclass
class BoardCardRow:
    """Card do Kanban (spec 051, regra 2) — mesmas peças de `LawsuitListRow`, mais
    `step_id` (a coluna) e o nome do responsável, sem `last_movement_title` (o board
    não mostra o último andamento, a listagem sim)."""

    lawsuit: Lawsuit
    lawsuit_type_name: str
    action_group_name: str
    stage_name: str
    step_id: int
    responsible_name: str
    parties: list[dict[str, object]]
    parties_total: int
    stagnant_days: int | None  # regra 7 (052): base do tooltip do badge de estagnação


@dataclass
class CrmStatsByStepRow:
    step_id: int
    total: int
    stagnant_count: int


@dataclass
class CrmStatsRow:
    """§5: `stats` do CRM — mesmos filtros do board (regra 8 da 051)."""

    total_lawsuits: int
    received_this_month: int
    total_value: Decimal
    stagnant_count: int
    stagnant_value: Decimal
    by_step: list[CrmStatsByStepRow]


def filters_from_query(payload: LawsuitFiltersQuery) -> LawsuitFilters:
    """Traduz o modelo de query string (multivalorados em CSV) para `LawsuitFilters`.

    Multivalorados chegam separados por vírgula; visão desconhecida cai no default
    (`QuickViews.resolve`)."""

    def uuids(raw: str | None) -> list[uuid.UUID]:
        return [uuid.UUID(value) for value in raw.split(",")] if raw else []

    def ints(raw: str | None) -> list[int]:
        return [int(value) for value in raw.split(",")] if raw else []

    contingencies: list[ContingencyLevel] = []
    if payload.contingency:
        contingencies = [ContingencyLevel(value) for value in payload.contingency.split(",")]
    return LawsuitFilters(
        view=LAWSUIT_VIEWS.resolve(payload.view),
        q=payload.q,
        customer_id=payload.customer_id,
        identification=payload.identification,
        process_number=payload.process_number,
        protocol_number=payload.protocol_number,
        folder=payload.folder,
        notes=payload.notes,
        action_group_ids=uuids(payload.action_group_id),
        lawsuit_type_ids=uuids(payload.lawsuit_type_id),
        step_ids=ints(payload.step_id),
        stage_ids=uuids(payload.stage_id),
        court_ids=ints(payload.court_id),
        court_system_ids=ints(payload.court_system_id),
        user_ids=uuids(payload.user_id),
        contingencies=contingencies,
        origin_ids=uuids(payload.origin_id),
        customer_type=payload.customer_type,
        created_from=payload.created_from,
        created_to=payload.created_to,
        process_date_from=payload.process_date_from,
        process_date_to=payload.process_date_to,
        closure_from=payload.closure_from,
        closure_to=payload.closure_to,
        transit_from=payload.transit_from,
        transit_to=payload.transit_to,
        archived_from=payload.archived_from,
        archived_to=payload.archived_to,
        archived=payload.archived,
        display_stagnant=payload.display_stagnant,
    )


def _party_exists(extra: ColumnElement[bool]) -> ColumnElement[bool]:
    """EXISTS em lawsuit_parties (join customers) — base dos filtros de parte
    (q, identification, origem, tipo de pessoa, customer_id)."""
    stmt = (
        select(LawsuitParty.id)
        .join(Customer, Customer.id == LawsuitParty.customer_id)
        .where(LawsuitParty.lawsuit_id == Lawsuit.id, extra)
    )
    return stmt.exists()


def _so_digitos(valor: str) -> str:
    return "".join(character for character in valor if character.isdigit())


def _text_search(q: str) -> ColumnElement[bool]:
    """Regra 5: nome de parte (sem acento, case-insensitive — mesmo padrão da busca de
    contatos da spec 019), número, protocolo e pasta, num único texto."""
    pattern = f"%{q}%"
    lowered = func.unaccent(func.lower(literal(q)))
    party_pattern = func.concat("%", lowered, "%")
    digits = _so_digitos(q)
    return or_(
        _party_exists(func.unaccent(func.lower(Customer.name)).ilike(party_pattern)),
        Lawsuit.protocol_number.ilike(pattern),
        Lawsuit.folder.ilike(pattern),
        Lawsuit.process_number.ilike(f"%{digits}%") if digits else text("false"),
    )


# Filtros que são só «coluna IN (valores)» — tabela em vez de uma cadeia de `if`, porque
# filtro novo desta forma passa a ser uma linha aqui (spec 106). Os que têm lógica de
# verdade (busca textual, documento, número do processo, estagnação) continuam explícitos
# abaixo: escondê-los numa tabela junto com os triviais é que seria perder informação.
_IN_FILTERS: tuple[tuple[str, InstrumentedAttribute[Any]], ...] = (
    ("action_group_ids", LawsuitType.action_group_id),
    ("lawsuit_type_ids", Lawsuit.lawsuit_type_id),
    ("step_ids", Stage.step_id),
    ("stage_ids", Lawsuit.stage_id),
    ("court_ids", Lawsuit.court_id),
    ("court_system_ids", Lawsuit.court_system_id),
    ("user_ids", Lawsuit.user_id),
    ("contingencies", Lawsuit.contingency),
)

# Filtros que são só «coluna ILIKE %texto%».
_ILIKE_FILTERS: tuple[tuple[str, InstrumentedAttribute[Any]], ...] = (
    ("protocol_number", Lawsuit.protocol_number),
    ("folder", Lawsuit.folder),
    ("notes", Lawsuit.notes),
)

# Intervalos de data/hora: (coluna, atributo do início, atributo do fim, helper).
_RANGE_FILTERS: tuple[tuple[InstrumentedAttribute[Any], str, str, Any], ...] = (
    (Lawsuit.created_at, "created_from", "created_to", datetime_range),
    (Lawsuit.process_date, "process_date_from", "process_date_to", date_range),
    (Lawsuit.closure_date, "closure_from", "closure_to", date_range),
    (Lawsuit.transit_date, "transit_from", "transit_to", date_range),
    (Lawsuit.archived_date, "archived_from", "archived_to", date_range),
)


def _party_conditions(filters: LawsuitFilters) -> list[ColumnElement[bool]]:
    """As que atravessam `lawsuit_parties` — `EXISTS` correlacionado, nunca `JOIN`, para
    um processo com três partes não aparecer três vezes."""
    condicoes: list[ColumnElement[bool]] = []
    if filters.customer_id is not None:
        condicoes.append(_party_exists(LawsuitParty.customer_id == filters.customer_id))
    if filters.identification:
        # Regra 6: CPF/CNPJ de qualquer parte — o documento é guardado só com dígitos.
        condicoes.append(
            _party_exists(Customer.identification == _so_digitos(filters.identification))
        )
    if filters.origin_ids:
        condicoes.append(_party_exists(Customer.origin_id.in_(filters.origin_ids)))
    if filters.customer_type:
        condicoes.append(_party_exists(Customer.type == filters.customer_type))
    return condicoes


def _build_conditions(filters: LawsuitFilters) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []

    view_condition = LAWSUIT_VIEWS.predicate(filters.view)
    if view_condition is not None:
        conditions.append(view_condition)
    if filters.q:
        conditions.append(_text_search(filters.q))
    if filters.process_number and (digits := _so_digitos(filters.process_number)):
        conditions.append(Lawsuit.process_number.ilike(f"%{digits}%"))

    conditions += _party_conditions(filters)
    conditions += _declarative_conditions(filters)
    conditions += _status_conditions(filters)
    return conditions


def _declarative_conditions(filters: LawsuitFilters) -> list[ColumnElement[bool]]:
    """As três tabelas: `IN`, `ILIKE` e intervalo. Cada uma só produz condição para o
    filtro que veio preenchido."""
    condicoes: list[ColumnElement[bool]] = [
        coluna.in_(valores)
        for atributo, coluna in _IN_FILTERS
        if (valores := getattr(filters, atributo))
    ]
    condicoes += [
        coluna.ilike(f"%{valor}%")
        for atributo, coluna in _ILIKE_FILTERS
        if (valor := getattr(filters, atributo))
    ]
    for coluna, inicio, fim, helper in _RANGE_FILTERS:
        condicoes += helper(coluna, getattr(filters, inicio), getattr(filters, fim))
    return condicoes


def _status_conditions(filters: LawsuitFilters) -> list[ColumnElement[bool]]:
    """Arquivado e estagnado: os dois são tri-estado — sim, não, ou tanto faz.

    `None` (e, na estagnação, qualquer valor fora do par) significa «não filtre», que é
    diferente de «filtre por falso». Um `if` que tratasse ausência como `False` esconderia
    metade dos processos da listagem sem ninguém pedir.
    """
    condicoes: list[ColumnElement[bool]] = []
    if filters.archived is not None:
        condicoes.append(Lawsuit.is_archived.is_(filters.archived))
    if filters.display_stagnant in ("stagnant", "active"):
        condicoes.append(Lawsuit.is_stagnant.is_(filters.display_stagnant == "stagnant"))
    return condicoes


class LawsuitListingRepository:
    """Query de listagem — não herda BaseRepository (não é CRUD)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _parties_subquery(self) -> Subquery:
        """Partes agregadas por processo (regra 12: as 2 primeiras + contador na UI) na
        MESMA query da página, nunca N+1. O SQLAlchemy desta versão não tem
        `aggregate_order_by`, então a ordenação polo/nome (regra 7 da spec 023) vem de
        uma subquery ordenada antes do json_agg — o Postgres agrega em scan order."""
        ordered = (
            select(
                LawsuitParty.lawsuit_id.label("lawsuit_id"),
                Customer.name.label("name"),
                LawsuitParty.pole.label("pole"),
            )
            .join(Customer, Customer.id == LawsuitParty.customer_id)
            .order_by(LawsuitParty.lawsuit_id, LawsuitParty.pole, Customer.name)
            .subquery()
        )
        return (
            select(
                ordered.c.lawsuit_id,
                func.json_agg(
                    func.json_build_object("name", ordered.c.name, "pole", ordered.c.pole),
                    type_=JSONB,
                ).label("parties"),
                func.count().label("parties_total"),
            )
            .group_by(ordered.c.lawsuit_id)
            .subquery()
        )

    def _last_movement_title(self) -> ScalarSelect[str]:
        return (
            select(LawsuitMovement.title)
            .where(LawsuitMovement.lawsuit_id == Lawsuit.id)
            .order_by(LawsuitMovement.occurred_at.desc(), LawsuitMovement.id)
            .limit(1)
            .scalar_subquery()
        )

    async def list_filtered(
        self,
        *,
        filters: LawsuitFilters,
        descending: bool = True,
        cursor: tuple[datetime, uuid.UUID] | None = None,
        limit: int = 20,
    ) -> tuple[Sequence[LawsuitListRow], int]:
        """Keyset por `created_at` (regra 11).

        Duas statements, mas não as de antes: a primeira escolhe os ids da página e traz
        o total do filtro por janela; a segunda resolve os rótulos das 20 linhas
        escolhidas. Ver o comentário do JOIN diferido abaixo.
        """
        conditions = _build_conditions(filters)
        parties = self._parties_subquery()

        # Spec 098, regra 1 — JOIN DIFERIDO. Escolher a página e resolver os rótulos na
        # MESMA query obriga o Postgres a materializar o conjunto filtrado inteiro antes
        # de ordenar: com 100 mil processos ele lia os 100 mil para devolver 20, em
        # 640 ms. Aqui a página sai primeiro, só de `lawsuits` (o `ORDER BY created_at`
        # com `LIMIT` vira leitura de índice), e os quatro JOINs de rótulo caem sobre as
        # 20 linhas escolhidas.
        sort_column = Lawsuit.created_at
        # O total do filtro sai por função de janela na PRÓPRIA query da página: é o
        # mesmo conjunto de linhas, e um `SELECT count(*)` separado percorreria a mesma
        # faixa duas vezes. Os dois JOINs continuam porque os filtros podem referenciar
        # etapa e tipo de ação — e são tabelas de dezenas de linhas.
        pagina_stmt = (
            select(Lawsuit.id, sort_column, func.count().over().label("total"))
            .select_from(Lawsuit)
            .join(LawsuitType, LawsuitType.id == Lawsuit.lawsuit_type_id)
            .join(Stage, Stage.id == Lawsuit.stage_id)
        )
        for condition in conditions:
            pagina_stmt = pagina_stmt.where(condition)
        pagina_stmt = paginate_keyset(
            pagina_stmt,
            sort_column=sort_column,
            id_column=Lawsuit.id,
            descending=descending,
            cursor=cursor,
            limit=limit,
        )
        linhas_da_pagina = (await self.session.execute(pagina_stmt)).all()
        # Página vazia é filtro sem resultado — a janela não existe e zero é o total.
        total = int(linhas_da_pagina[0].total) if linhas_da_pagina else 0
        ids_da_pagina = [linha[0] for linha in linhas_da_pagina]
        if not ids_da_pagina:
            return [], total

        stmt = (
            select(
                Lawsuit,
                LawsuitType.name,
                ActionGroup.name,
                Stage.name,
                parties.c.parties,
                parties.c.parties_total,
                self._last_movement_title().label("last_movement_title"),
            )
            .join(LawsuitType, LawsuitType.id == Lawsuit.lawsuit_type_id)
            .join(ActionGroup, ActionGroup.id == LawsuitType.action_group_id)
            .join(Stage, Stage.id == Lawsuit.stage_id)
            .outerjoin(parties, parties.c.lawsuit_id == Lawsuit.id)
            .where(Lawsuit.id.in_(ids_da_pagina))
        )
        # A ordenação precisa ser repetida: `IN` não preserva ordem nenhuma, e a página
        # sairia embaralhada em relação ao cursor que a produziu.
        ordem = sort_column.desc() if descending else sort_column.asc()
        desempate = Lawsuit.id.desc() if descending else Lawsuit.id.asc()
        stmt = stmt.order_by(ordem, desempate)

        rows = (await self.session.execute(stmt)).all()
        items = [
            LawsuitListRow(
                lawsuit=row[0],
                lawsuit_type_name=row[1],
                action_group_name=row[2],
                stage_name=row[3],
                parties=list(row[4] or []),
                parties_total=row[5] or 0,
                last_movement_title=row[6],
            )
            for row in rows
        ]
        return items, total

    def _board_select(self, conditions: list[ColumnElement[bool]]) -> Select[Any]:
        """Shape comum de `board`/`board_column`. Any: `Select` composto de 8 colunas
        heterogêneas (entidade + nomes + agregados) — mesmo padrão de `Select[Any]`
        genérico já usado em `core/listing.py::paginate_keyset`."""
        parties = self._parties_subquery()
        stmt = (
            select(
                Lawsuit,
                LawsuitType.name,
                ActionGroup.name,
                Stage.name,
                Stage.step_id,
                User.name,
                parties.c.parties,
                parties.c.parties_total,
                Stage.stagnant_days,
            )
            .join(LawsuitType, LawsuitType.id == Lawsuit.lawsuit_type_id)
            .join(ActionGroup, ActionGroup.id == LawsuitType.action_group_id)
            .join(Stage, Stage.id == Lawsuit.stage_id)
            .join(User, User.id == Lawsuit.user_id)
            .outerjoin(parties, parties.c.lawsuit_id == Lawsuit.id)
        )
        for condition in conditions:
            stmt = stmt.where(condition)
        return stmt

    @staticmethod
    def _row_to_board_card(row: Row[Any]) -> BoardCardRow:
        return BoardCardRow(
            lawsuit=row[0],
            lawsuit_type_name=row[1],
            action_group_name=row[2],
            stage_name=row[3],
            step_id=row[4],
            responsible_name=row[5],
            parties=list(row[6] or []),
            parties_total=row[7] or 0,
            stagnant_days=row[8],
        )

    async def board_counts(self, *, filters: LawsuitFilters) -> dict[int, int]:
        """Totais reais por fase (regra 7: "o contador mostra o total real", mesmo
        além do `limit_per_column`) — 1 statement."""
        conditions = _build_conditions(filters)
        stmt = (
            select(Stage.step_id, func.count())
            .select_from(Lawsuit)
            .join(LawsuitType, LawsuitType.id == Lawsuit.lawsuit_type_id)
            .join(Stage, Stage.id == Lawsuit.stage_id)
            .group_by(Stage.step_id)
        )
        for condition in conditions:
            stmt = stmt.where(condition)
        return dict((await self.session.execute(stmt)).tuples().all())

    async def board(
        self, *, filters: LawsuitFilters, limit_per_column: int = BOARD_DEFAULT_LIMIT_PER_COLUMN
    ) -> dict[int, list[BoardCardRow]]:
        """Board Kanban (spec 051, regras 1/3/7): até `limit_per_column` cards por fase,
        A fase (`step_id`) vem de um ranking por janela, materializado antes do JOIN
        (spec 098, regra 1 — ver comentário abaixo)."""
        conditions = _build_conditions(filters)
        rank_subq = (
            select(
                Lawsuit.id,
                func.row_number()
                .over(
                    partition_by=Stage.step_id,
                    order_by=(Lawsuit.stage_entered_at.desc(), Lawsuit.id),
                )
                .label("rn"),
            )
            .join(LawsuitType, LawsuitType.id == Lawsuit.lawsuit_type_id)
            .join(Stage, Stage.id == Lawsuit.stage_id)
        )
        for condition in conditions:
            rank_subq = rank_subq.where(condition)
        ranked = rank_subq.subquery()
        # Spec 098, regra 1: o ranking é MATERIALIZADO antes do JOIN. Como subconsulta de
        # `IN (...)`, a janela `row_number() OVER (PARTITION BY step_id)` — que precisa
        # ordenar o conjunto filtrado inteiro — era avaliada dentro da query de cards, e
        # o planejador a executava junto do JOIN de rótulos sobre 100 mil linhas. Rodando
        # antes, ela sai uma vez e o JOIN recebe algumas dezenas de ids literais.
        ids_query = select(ranked.c.id).where(ranked.c.rn <= limit_per_column)
        ranked_ids = list((await self.session.scalars(ids_query)).all())
        if not ranked_ids:
            return {}

        stmt = self._board_select(conditions).where(Lawsuit.id.in_(ranked_ids))
        stmt = stmt.order_by(Stage.step_id, Lawsuit.stage_entered_at.desc(), Lawsuit.id)
        rows = (await self.session.execute(stmt)).all()

        cards_by_step: dict[int, list[BoardCardRow]] = {}
        for row in rows:
            card = self._row_to_board_card(row)
            cards_by_step.setdefault(card.step_id, []).append(card)
        return cards_by_step

    async def board_column(
        self,
        *,
        filters: LawsuitFilters,
        step_id: int,
        cursor: tuple[datetime, uuid.UUID] | None,
        limit: int,
    ) -> tuple[Sequence[BoardCardRow], int]:
        """Paginação de UMA coluna (regra 7, `GET /crm/board/column/{step_id}`) —
        keyset por `stage_entered_at`, mesmo critério de ordenação do board inicial."""
        conditions = [*_build_conditions(filters), Stage.step_id == step_id]

        count_stmt = (
            select(func.count())
            .select_from(Lawsuit)
            .join(LawsuitType, LawsuitType.id == Lawsuit.lawsuit_type_id)
            .join(Stage, Stage.id == Lawsuit.stage_id)
        )
        for condition in conditions:
            count_stmt = count_stmt.where(condition)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = paginate_keyset(
            self._board_select(conditions),
            sort_column=Lawsuit.stage_entered_at,
            id_column=Lawsuit.id,
            descending=True,
            cursor=cursor,
            limit=limit,
        )
        rows = (await self.session.execute(stmt)).all()
        return [self._row_to_board_card(row) for row in rows], total

    async def crm_stats(self, *, filters: LawsuitFilters) -> CrmStatsRow:
        """§5: cards de topo do CRM — 2 statements (totais + quebra por fase)."""
        conditions = _build_conditions(filters)

        def _base(*columns: Any) -> Select[Any]:
            stmt: Select[Any] = (
                select(*columns)
                .select_from(Lawsuit)
                .join(LawsuitType, LawsuitType.id == Lawsuit.lawsuit_type_id)
                .join(Stage, Stage.id == Lawsuit.stage_id)
            )
            for condition in conditions:
                stmt = stmt.where(condition)
            return stmt

        received_this_month = Lawsuit.created_at >= func.date_trunc("month", func.now())
        totals_stmt = _base(
            func.count(),
            func.count().filter(received_this_month),
            func.coalesce(func.sum(Lawsuit.case_value), 0),
            func.count().filter(Lawsuit.is_stagnant.is_(True)),
            func.coalesce(func.sum(Lawsuit.case_value).filter(Lawsuit.is_stagnant.is_(True)), 0),
        )
        total, received, total_value, stagnant_count, stagnant_value = (
            await self.session.execute(totals_stmt)
        ).one()

        by_step_stmt = _base(
            Stage.step_id, func.count(), func.count().filter(Lawsuit.is_stagnant.is_(True))
        ).group_by(Stage.step_id)
        by_step_rows = (await self.session.execute(by_step_stmt)).all()

        return CrmStatsRow(
            total_lawsuits=total,
            received_this_month=received,
            total_value=total_value,
            stagnant_count=stagnant_count,
            stagnant_value=stagnant_value,
            by_step=[
                CrmStatsByStepRow(step_id=row[0], total=row[1], stagnant_count=row[2])
                for row in by_step_rows
            ],
        )
