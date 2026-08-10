import base64
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, and_, func, literal, or_, select, union_all
from sqlalchemy.sql.selectable import Subquery

from app.core.repository import BaseRepository
from app.domain.customers.models import Customer
from app.domain.lawsuits.models import (
    Lawsuit,
    LawsuitMovement,
    LawsuitParty,
    MovementOrigin,
    PartyPole,
)
from app.domain.users.models import User

# Os 5 tipos da timeline (spec 026 §4). Os slots `task`/`publication`/`transaction` ficam
# sem fonte até as specs 032/042/056 — não entram no union enquanto a tabela não existe.
TIMELINE_KINDS = ("task", "movement_auto", "movement_manual", "publication", "transaction")

_MOVEMENT_KIND_BY_ORIGIN = {
    "movement_auto": MovementOrigin.TRIBUNAL,
    "movement_manual": MovementOrigin.MANUAL,
}


@dataclass
class TimelineRow:
    kind: str
    id: uuid.UUID
    occurred_at: datetime
    title: str
    summary: str | None
    actor: str | None
    header: str | None
    external_code: int | None


def encode_timeline_cursor(occurred_at: datetime, kind: str, id_: uuid.UUID) -> str:
    """Cursor opaco da timeline — codifica `(occurred_at, kind, id)`, as 3 chaves da
    ordenação estável (regra 1: timestamp, depois tipo, depois id)."""
    raw = json.dumps([occurred_at.isoformat(), kind, str(id_)], separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_timeline_cursor(cursor: str) -> tuple[datetime, str, uuid.UUID]:
    occurred_at, kind, id_str = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
    return datetime.fromisoformat(occurred_at), kind, uuid.UUID(id_str)


class LawsuitRepository(BaseRepository[Lawsuit]):
    model = Lawsuit

    async def find_by_process_number_digits(self, digits: str) -> Sequence[Lawsuit]:
        """Casamento por número (spec 045, regra 9): compara só dígitos — o processo
        pode estar salvo com ou sem máscara CNJ."""
        stmt = select(Lawsuit).where(
            func.regexp_replace(Lawsuit.process_number, r"\D", "", "g") == digits
        )
        return (await self.session.scalars(stmt)).all()

    async def list_by_responsible(self, user_id: uuid.UUID) -> Sequence[Lawsuit]:
        """Candidatos da estratégia 2 de casamento (spec 045, §5) — processos do
        advogado identificado pelo termo monitorado que capturou a publicação."""
        stmt = select(Lawsuit).where(Lawsuit.user_id == user_id)
        return (await self.session.scalars(stmt)).all()


class LawsuitPartyRepository(BaseRepository[LawsuitParty]):
    model = LawsuitParty

    async def list_for_lawsuit(self, lawsuit_id: uuid.UUID) -> Sequence[tuple[LawsuitParty, str]]:
        """Partes com o nome do contato, na ordem de exibição da regra 7:
        polo (ATIVO → PASSIVO → CONTRARIA → TERCEIRO — ordem natural do enum) e,
        dentro do polo, alfabética."""
        stmt = (
            select(LawsuitParty, Customer.name)
            .join(Customer, Customer.id == LawsuitParty.customer_id)
            .where(LawsuitParty.lawsuit_id == lawsuit_id)
            .order_by(LawsuitParty.pole, Customer.name)
        )
        result = await self.session.execute(stmt)
        return result.tuples().all()

    async def find_duplicate(
        self,
        *,
        lawsuit_id: uuid.UUID,
        customer_id: uuid.UUID,
        pole: PartyPole,
        exclude_id: uuid.UUID | None = None,
    ) -> LawsuitParty | None:
        stmt = select(LawsuitParty).where(
            LawsuitParty.lawsuit_id == lawsuit_id,
            LawsuitParty.customer_id == customer_id,
            LawsuitParty.pole == pole,
        )
        if exclude_id is not None:
            stmt = stmt.where(LawsuitParty.id != exclude_id)
        result = await self.session.scalars(stmt)
        return result.first()

    async def count_for_lawsuit(self, lawsuit_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(LawsuitParty)
            .where(LawsuitParty.lawsuit_id == lawsuit_id)
        )
        return await self.session.scalar(stmt) or 0


class LawsuitMovementRepository(BaseRepository[LawsuitMovement]):
    model = LawsuitMovement

    async def find_by_external_id(
        self, lawsuit_id: uuid.UUID, external_id: str
    ) -> LawsuitMovement | None:
        stmt = select(LawsuitMovement).where(
            LawsuitMovement.lawsuit_id == lawsuit_id,
            LawsuitMovement.external_id == external_id,
        )
        result = await self.session.scalars(stmt)
        return result.first()

    def _timeline_union(self, lawsuit_id: uuid.UUID, kinds: Sequence[str]) -> Subquery | None:
        sources: list[
            Select[tuple[uuid.UUID, datetime, str, str, str | None, str, str | None, int | None]]
        ] = []
        for kind in kinds:
            origin = _MOVEMENT_KIND_BY_ORIGIN.get(kind)
            if origin is None:
                continue  # slot sem fonte ainda (task/publication/transaction)
            sources.append(
                select(
                    LawsuitMovement.id,
                    LawsuitMovement.occurred_at,
                    literal(kind).label("kind"),
                    LawsuitMovement.title,
                    LawsuitMovement.body.label("summary"),
                    User.name.label("actor"),
                    LawsuitMovement.header,
                    LawsuitMovement.external_code,
                )
                .select_from(LawsuitMovement)
                .outerjoin(User, User.id == LawsuitMovement.created_by)
                .where(
                    LawsuitMovement.lawsuit_id == lawsuit_id,
                    LawsuitMovement.origin == origin,
                )
            )
        if not sources:
            return None
        return union_all(*sources).subquery()

    async def list_timeline(
        self,
        lawsuit_id: uuid.UUID,
        *,
        kinds: Sequence[str],
        cursor: tuple[datetime, str, uuid.UUID] | None,
        limit: int,
    ) -> tuple[Sequence[TimelineRow], int]:
        """Timeline unificada (spec 026): agregação por UNION ALL das fontes pedidas
        (regra 8 — nunca N+1), ordenação estável `occurred_at DESC, kind, id` (regra 1) e
        paginação keyset pelo mesmo trio (regra 6). Duas statements no total (página +
        contagem dos kinds, sem o filtro de cursor — `total` não muda entre páginas)."""
        sources = self._timeline_union(lawsuit_id, kinds)
        if sources is None:
            return [], 0

        timeline = sources
        total = await self.session.scalar(select(func.count()).select_from(timeline))

        stmt = select(timeline)
        if cursor is not None:
            cursor_at, cursor_kind, cursor_id = cursor
            # Ordem mista (DESC, ASC, ASC) não cabe numa comparação de tupla só —
            # o predicado exato é o desdobramento lexicográfico das 3 chaves.
            stmt = stmt.where(
                or_(
                    timeline.c.occurred_at < cursor_at,
                    and_(
                        timeline.c.occurred_at == cursor_at,
                        timeline.c.kind > cursor_kind,
                    ),
                    and_(
                        timeline.c.occurred_at == cursor_at,
                        timeline.c.kind == cursor_kind,
                        timeline.c.id > cursor_id,
                    ),
                )
            )
        stmt = stmt.order_by(timeline.c.occurred_at.desc(), timeline.c.kind, timeline.c.id).limit(
            limit
        )
        rows = (await self.session.execute(stmt)).all()
        items = [
            TimelineRow(
                kind=row.kind,
                id=row.id,
                occurred_at=row.occurred_at,
                title=row.title,
                summary=row.summary,
                actor=row.actor,
                header=row.header,
                external_code=row.external_code,
            )
            for row in rows
        ]
        return items, total or 0
