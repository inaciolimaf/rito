"""Listagem de processos (spec 027): 12 visões rápidas + filtros combináveis.

Separado de `repository.py` (SRP): aqui só vive a query de listagem — a mais exigente do
módulo (partes agregadas sem N+1, último andamento correlacionado, keyset).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time

from sqlalchemy import ColumnElement, and_, func, literal, or_, select, text, tuple_
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import ScalarSelect, Subquery

from app.domain.action_groups.models import ActionGroup, LawsuitType
from app.domain.customers.models import Customer
from app.domain.lawsuits.models import (
    ContingencyLevel,
    Lawsuit,
    LawsuitMovement,
    LawsuitParty,
)
from app.domain.stages.models import Stage

# As 12 visões rápidas (spec 027 §5).
LAWSUIT_VIEWS = (
    "all",
    "active",
    "moved_30d",
    "moved_7d",
    "moved_today",
    "never_captured",
    "idle_30d",
    "idle_45d",
    "idle_90d",
    "closed_this_month",
    "filed_this_month",
    "archived_this_month",
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


@dataclass
class LawsuitListRow:
    lawsuit: Lawsuit
    lawsuit_type_name: str
    action_group_name: str
    stage_name: str
    parties: list[dict[str, object]]
    parties_total: int
    last_movement_title: str | None


def _view_filter(view: str) -> ColumnElement[bool] | None:
    """As 12 visões (regras 2–4) — atalho combinável com filtros (regra 1)."""
    now = func.now()
    if view == "all":
        return None
    if view == "active":
        # Regra 2: ativo = não arquivado (visibilidade) E sem data de arquivamento (fato).
        return and_(Lawsuit.is_archived.is_(False), Lawsuit.archived_date.is_(None))
    if view == "moved_30d":
        return Lawsuit.last_movement_at >= now - text("interval '30 days'")
    if view == "moved_7d":
        return Lawsuit.last_movement_at >= now - text("interval '7 days'")
    if view == "moved_today":
        return Lawsuit.last_movement_at >= func.date_trunc("day", func.now())
    if view == "never_captured":
        return Lawsuit.last_movement_at.is_(None)
    if view in ("idle_30d", "idle_45d", "idle_90d"):
        days = int(view.removeprefix("idle_").removesuffix("d"))
        # Regra 3: parado há N dias ou nunca movimentado.
        return or_(
            Lawsuit.last_movement_at.is_(None),
            Lawsuit.last_movement_at < now - text(f"interval '{days} days'"),
        )
    if view == "closed_this_month":
        return Lawsuit.closure_date >= func.date_trunc("month", func.current_date())
    if view == "filed_this_month":
        return Lawsuit.process_date >= func.date_trunc("month", func.current_date())
    if view == "archived_this_month":
        return Lawsuit.archived_date >= func.date_trunc("month", func.current_date())
    return None


def _party_exists(extra: ColumnElement[bool]) -> ColumnElement[bool]:
    """EXISTS em lawsuit_parties (join customers) — base dos filtros de parte
    (q, identification, origem, tipo de pessoa, customer_id)."""
    stmt = (
        select(LawsuitParty.id)
        .join(Customer, Customer.id == LawsuitParty.customer_id)
        .where(LawsuitParty.lawsuit_id == Lawsuit.id, extra)
    )
    return stmt.exists()


def _build_conditions(filters: LawsuitFilters) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []

    view_condition = _view_filter(filters.view)
    if view_condition is not None:
        conditions.append(view_condition)

    if filters.q:
        # Regra 5: nome de parte (sem acento, case-insensitive — mesmo padrão da busca
        # de contatos da spec 019), número, protocolo e pasta — um único texto.
        pattern = f"%{filters.q}%"
        lowered = func.unaccent(func.lower(literal(filters.q)))
        party_pattern = func.concat("%", lowered, "%")
        digits = "".join(character for character in filters.q if character.isdigit())
        conditions.append(
            or_(
                _party_exists(func.unaccent(func.lower(Customer.name)).ilike(party_pattern)),
                Lawsuit.protocol_number.ilike(pattern),
                Lawsuit.folder.ilike(pattern),
                Lawsuit.process_number.ilike(f"%{digits}%") if digits else text("false"),
            )
        )
    if filters.customer_id is not None:
        conditions.append(_party_exists(LawsuitParty.customer_id == filters.customer_id))
    if filters.identification:
        # Regra 6: CPF/CNPJ de qualquer parte — o documento é guardado só com dígitos.
        digits = "".join(c for c in filters.identification if c.isdigit())
        conditions.append(_party_exists(Customer.identification == digits))
    if filters.process_number:
        digits = "".join(c for c in filters.process_number if c.isdigit())
        if digits:
            conditions.append(Lawsuit.process_number.ilike(f"%{digits}%"))
    if filters.protocol_number:
        conditions.append(Lawsuit.protocol_number.ilike(f"%{filters.protocol_number}%"))
    if filters.folder:
        conditions.append(Lawsuit.folder.ilike(f"%{filters.folder}%"))
    if filters.notes:
        conditions.append(Lawsuit.notes.ilike(f"%{filters.notes}%"))

    if filters.action_group_ids:
        conditions.append(LawsuitType.action_group_id.in_(filters.action_group_ids))
    if filters.lawsuit_type_ids:
        conditions.append(Lawsuit.lawsuit_type_id.in_(filters.lawsuit_type_ids))
    if filters.step_ids:
        conditions.append(Stage.step_id.in_(filters.step_ids))
    if filters.stage_ids:
        conditions.append(Lawsuit.stage_id.in_(filters.stage_ids))
    if filters.court_ids:
        conditions.append(Lawsuit.court_id.in_(filters.court_ids))
    if filters.court_system_ids:
        conditions.append(Lawsuit.court_system_id.in_(filters.court_system_ids))
    if filters.user_ids:
        conditions.append(Lawsuit.user_id.in_(filters.user_ids))
    if filters.contingencies:
        conditions.append(Lawsuit.contingency.in_(filters.contingencies))
    if filters.origin_ids:
        conditions.append(_party_exists(Customer.origin_id.in_(filters.origin_ids)))
    if filters.customer_type:
        conditions.append(_party_exists(Customer.type == filters.customer_type))

    if filters.created_from is not None:
        conditions.append(Lawsuit.created_at >= datetime.combine(filters.created_from, time.min))
    if filters.created_to is not None:
        conditions.append(Lawsuit.created_at <= datetime.combine(filters.created_to, time.max))
    if filters.process_date_from is not None:
        conditions.append(Lawsuit.process_date >= filters.process_date_from)
    if filters.process_date_to is not None:
        conditions.append(Lawsuit.process_date <= filters.process_date_to)
    if filters.closure_from is not None:
        conditions.append(Lawsuit.closure_date >= filters.closure_from)
    if filters.closure_to is not None:
        conditions.append(Lawsuit.closure_date <= filters.closure_to)
    if filters.transit_from is not None:
        conditions.append(Lawsuit.transit_date >= filters.transit_from)
    if filters.transit_to is not None:
        conditions.append(Lawsuit.transit_date <= filters.transit_to)
    if filters.archived_from is not None:
        conditions.append(Lawsuit.archived_date >= filters.archived_from)
    if filters.archived_to is not None:
        conditions.append(Lawsuit.archived_date <= filters.archived_to)
    if filters.archived is not None:
        conditions.append(Lawsuit.is_archived.is_(filters.archived))

    return conditions


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
        """Keyset por `created_at` (regra 11) — 2 statements (contagem + página)."""
        conditions = _build_conditions(filters)
        parties = self._parties_subquery()

        count_stmt = (
            select(func.count())
            .select_from(Lawsuit)
            .join(LawsuitType, LawsuitType.id == Lawsuit.lawsuit_type_id)
            .join(Stage, Stage.id == Lawsuit.stage_id)
        )
        for condition in conditions:
            count_stmt = count_stmt.where(condition)
        total = (await self.session.execute(count_stmt)).scalar_one()

        sort_column = Lawsuit.created_at
        order_column = sort_column.desc() if descending else sort_column.asc()
        id_column = Lawsuit.id.desc() if descending else Lawsuit.id.asc()
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
            .order_by(order_column, id_column)
            .limit(limit)
        )
        for condition in conditions:
            stmt = stmt.where(condition)
        if cursor is not None:
            cursor_value, cursor_id = cursor
            pair = tuple_(sort_column, Lawsuit.id)
            cursor_pair = tuple_(literal(cursor_value), literal(cursor_id))
            stmt = stmt.where(pair < cursor_pair if descending else pair > cursor_pair)

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
