import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import ColumnElement, exists, func, select

from app.core.listing import date_range, paginate_keyset
from app.core.repository import BaseRepository
from app.domain.lawsuits.models import LawsuitParty
from app.domain.publications.models import (
    Publication,
    PublicationLawyer,
    PublicationRead,
    PublicationRecipient,
)


@dataclass
class PublicationFilterParams:
    """Filtros combináveis do §5 (spec 048) — `linked`/`cancelled`/`read` ficam de
    fora daqui quando usados só pelos contadores (regra: uma query só, os 3 juntos)."""

    availability_from: date | None = None
    availability_to: date | None = None
    routed_to: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    court_code: str | None = None
    process_number_digits: str | None = None
    linked: bool | None = None
    cancelled: bool | None = None
    read: bool | None = None
    current_user_id: uuid.UUID | None = None  # exige quando `read` é usado


@dataclass
class PublicationCounts:
    total: int
    unlinked: int
    cancelled: int
    unread: int


@dataclass
class PublicationMetricsRow:
    """Insumo cru pra `PublicationMetricsService` (spec 049, §7) — período/taxa
    ficam por conta do service, aqui é só agregação de banco."""

    total: int
    auto_linked: int
    per_day: dict[date, int]
    per_court: dict[str, int]


# regra 7 da 049: casamento automático é `process_number`/`lawyer_id` — `manual`
# e `ambiguous` não contam como vínculo automático.
_AUTO_MATCHED_BY = ("process_number", "lawyer_id")


@dataclass
class PublicationListRow:
    """Linha enriquecida (spec 048) — partes e nome do responsável resolvidos sem
    N+1, reaproveitada pela listagem e pelo export (mesmo padrão de `LawsuitListRow`,
    spec 027)."""

    publication: Publication
    parties: list[str]
    routed_to_name: str | None
    is_read: bool


class PublicationRepository(BaseRepository[Publication]):
    model = Publication

    async def get_by_hash(self, hash_: str) -> Publication | None:
        result = await self.session.scalars(select(Publication).where(Publication.hash == hash_))
        return result.first()

    def _base_conditions(self, filters: PublicationFilterParams) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = []
        conditions += date_range(
            Publication.availability_date, filters.availability_from, filters.availability_to
        )
        if filters.routed_to is not None:
            conditions.append(Publication.routed_to == filters.routed_to)
        if filters.customer_id is not None:
            conditions.append(
                Publication.lawsuit_id.in_(
                    select(LawsuitParty.lawsuit_id).where(
                        LawsuitParty.customer_id == filters.customer_id
                    )
                )
            )
        if filters.court_code is not None:
            conditions.append(Publication.court_code == filters.court_code)
        if filters.process_number_digits:
            # Regra 11: busca aceita com ou sem máscara — o lado da coluna já é só
            # dígitos (spec 042, regra 4); o chamador normaliza o lado da busca.
            conditions.append(Publication.process_number == filters.process_number_digits)
        return conditions

    def _read_exists(self, user_id: uuid.UUID) -> ColumnElement[bool]:
        return exists().where(
            PublicationRead.publication_id == Publication.id,
            PublicationRead.user_id == user_id,
        )

    def _toggle_conditions(self, filters: PublicationFilterParams) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = []
        if filters.linked is not None:
            condition = Publication.lawsuit_id.is_not(None)
            conditions.append(condition if filters.linked else ~condition)
        if filters.cancelled is not None:
            condition = Publication.is_active.is_(False)
            conditions.append(condition if filters.cancelled else ~condition)
        if filters.read is not None:
            assert filters.current_user_id is not None
            read_exists = self._read_exists(filters.current_user_id)
            conditions.append(read_exists if filters.read else ~read_exists)
        return conditions

    async def list_filtered(
        self,
        *,
        filters: PublicationFilterParams,
        cursor: tuple[date, uuid.UUID] | None,
        limit: int,
    ) -> tuple[Sequence[Publication], int]:
        """Regra 10: keyset por `(availability_date, id)`, sempre mais recente primeiro."""
        conditions = self._base_conditions(filters) + self._toggle_conditions(filters)

        count_stmt = select(func.count()).select_from(Publication)
        for condition in conditions:
            count_stmt = count_stmt.where(condition)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = select(Publication)
        for condition in conditions:
            stmt = stmt.where(condition)
        stmt = paginate_keyset(
            stmt,
            sort_column=Publication.availability_date,
            id_column=Publication.id,
            descending=True,
            cursor=cursor,
            limit=limit,
        )
        items = (await self.session.scalars(stmt)).all()
        return items, total

    async def counts(
        self, *, filters: PublicationFilterParams, current_user_id: uuid.UUID
    ) -> PublicationCounts:
        """Regra do §8: os 3 contadores (não vinculadas/canceladas/não lidas) numa
        query só, sobre o MESMO filtro-base (interval/tribunal/etc — sem os toggles)."""
        conditions = self._base_conditions(filters)
        read_exists = self._read_exists(current_user_id)
        stmt = select(
            func.count(),
            func.count().filter(Publication.lawsuit_id.is_(None)),
            func.count().filter(Publication.is_active.is_(False)),
            func.count().filter(~read_exists),
        ).select_from(Publication)
        for condition in conditions:
            stmt = stmt.where(condition)
        total, unlinked, cancelled, unread = (await self.session.execute(stmt)).one()
        return PublicationCounts(total=total, unlinked=unlinked, cancelled=cancelled, unread=unread)

    async def metrics(self, *, since: date) -> PublicationMetricsRow:
        """Spec 049, regra 7: publicações por dia e por tribunal, mais o total
        casado automaticamente (base da taxa de vínculo automático da regra 8)."""
        totals_stmt = (
            select(
                func.count(),
                func.count().filter(Publication.matched_by.in_(_AUTO_MATCHED_BY)),
            )
            .select_from(Publication)
            .where(Publication.availability_date >= since)
        )
        total, auto_linked = (await self.session.execute(totals_stmt)).one()

        per_day_stmt = (
            select(Publication.availability_date, func.count())
            .where(Publication.availability_date >= since)
            .group_by(Publication.availability_date)
            .order_by(Publication.availability_date)
        )
        per_day = dict((await self.session.execute(per_day_stmt)).tuples().all())

        per_court_stmt = (
            select(Publication.court_code, func.count())
            .where(Publication.availability_date >= since)
            .group_by(Publication.court_code)
            .order_by(Publication.court_code)
        )
        per_court = dict((await self.session.execute(per_court_stmt)).tuples().all())

        return PublicationMetricsRow(
            total=total, auto_linked=auto_linked, per_day=per_day, per_court=per_court
        )


class PublicationRecipientRepository(BaseRepository[PublicationRecipient]):
    model = PublicationRecipient

    async def list_for_publication(
        self, publication_id: uuid.UUID
    ) -> Sequence[PublicationRecipient]:
        stmt = select(PublicationRecipient).where(
            PublicationRecipient.publication_id == publication_id
        )
        return (await self.session.scalars(stmt)).all()

    async def names_for_many(
        self, publication_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[str]]:
        """Nomes das partes de várias publicações em UMA query (sem N+1) — usado
        pela listagem e pelo export (spec 048)."""
        if not publication_ids:
            return {}
        stmt = (
            select(PublicationRecipient.publication_id, PublicationRecipient.name)
            .where(PublicationRecipient.publication_id.in_(publication_ids))
            .order_by(PublicationRecipient.name)
        )
        result: dict[uuid.UUID, list[str]] = {pub_id: [] for pub_id in publication_ids}
        for publication_id, name in await self.session.execute(stmt):
            result[publication_id].append(str(name))
        return result


class PublicationLawyerRepository(BaseRepository[PublicationLawyer]):
    model = PublicationLawyer

    async def list_for_publication(self, publication_id: uuid.UUID) -> Sequence[PublicationLawyer]:
        stmt = select(PublicationLawyer).where(PublicationLawyer.publication_id == publication_id)
        return (await self.session.scalars(stmt)).all()


class PublicationReadRepository(BaseRepository[PublicationRead]):
    model = PublicationRead

    async def get_for(
        self, publication_id: uuid.UUID, user_id: uuid.UUID
    ) -> PublicationRead | None:
        stmt = select(PublicationRead).where(
            PublicationRead.publication_id == publication_id,
            PublicationRead.user_id == user_id,
        )
        return (await self.session.scalars(stmt)).first()

    async def read_publication_ids(
        self, user_id: uuid.UUID, publication_ids: Sequence[uuid.UUID]
    ) -> set[uuid.UUID]:
        """Quais das publicações já foram lidas por ESTE usuário (regra 5) — uma
        query só para a página inteira."""
        if not publication_ids:
            return set()
        stmt = select(PublicationRead.publication_id).where(
            PublicationRead.user_id == user_id,
            PublicationRead.publication_id.in_(publication_ids),
        )
        return set((await self.session.scalars(stmt)).all())
