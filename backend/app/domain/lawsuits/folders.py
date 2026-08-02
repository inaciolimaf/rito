"""Pastas de processos (spec 029): autocomplete, renomear em lote e visão agrupada.

Pasta é atributo (`lawsuits.folder`), não entidade — toda a lógica é consulta/UPDATE
sobre `lawsuits`, com o tenant garantido pelo RLS (nunca por WHERE). A comparação de
nomes é case-insensitive e sem acento (regra 2) via `immutable_unaccent` (migration
014); o armazenamento preserva a grafia digitada.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from app.domain.lawsuits.exceptions import (
    FolderMergeNotConfirmedError,
    FolderNotFoundError,
)
from app.domain.lawsuits.models import Lawsuit

# Regra 7: autocomplete devolve no máximo 20 sugestões, por frequência de uso.
MAX_SUGGESTIONS = 20
# Teto da visão agrupada (regra 6): grupos por contagem decrescente, primeiros itens de
# cada grupo — a lista completa da pasta fica na listagem filtrada (?folder=).
MAX_GROUPS = 50
ITEMS_PER_GROUP = 10
NO_FOLDER_LABEL = "Sem pasta"


def _normalized(column: InstrumentedAttribute[str | None]) -> ColumnElement[str]:
    """Regra 2: comparação sem acento e sem diferenciar maiúsculas/minúsculas."""
    return func.immutable_unaccent(func.lower(column))


@dataclass
class FolderCount:
    name: str | None  # None = "Sem pasta" (regra 6)
    count: int


@dataclass
class FolderGroupItem:
    id: uuid.UUID
    process_number: str | None
    folder: str | None
    is_archived: bool
    created_at: datetime


@dataclass
class FolderGroup:
    name: str
    count: int
    items: Sequence[FolderGroupItem]


@dataclass
class FolderRenameResult:
    folder: str  # grafia final armazenada (a do alvo existente, em caso de fusão)
    updated: int
    merged: bool


class FolderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search(self, query: str | None, limit: int) -> Sequence[FolderCount]:
        stmt = (
            select(Lawsuit.folder, func.count().label("count"))
            .where(Lawsuit.folder.is_not(None))
            .group_by(Lawsuit.folder)
            .order_by(func.count().desc(), Lawsuit.folder)
            .limit(min(limit, MAX_SUGGESTIONS))
        )
        if query:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            # Regra 2: o padrão também passa por unaccent/lower — "acao" acha "Ação".
            stmt = stmt.where(
                _normalized(Lawsuit.folder).like(
                    func.immutable_unaccent(func.lower(f"%{escaped}%")), escape="\\"
                )
            )
        rows = await self.session.execute(stmt)
        return [FolderCount(name=str(name), count=int(count)) for name, count in rows]

    async def count_matching(self, name: str) -> int:
        stmt = select(func.count()).select_from(Lawsuit).where(_matches(name))
        return int((await self.session.execute(stmt)).scalar_one())

    async def is_same_normalized(self, first: str, second: str) -> bool:
        normalized_first = func.immutable_unaccent(func.lower(first))
        normalized_second = func.immutable_unaccent(func.lower(second))
        stmt = select(normalized_first == normalized_second)
        return bool((await self.session.execute(stmt)).scalar_one())

    async def distinct_matching(self, name: str) -> Sequence[str]:
        """Grafias armazenadas que casam com `name` (regra 2), da mais usada à menos."""
        stmt = (
            select(Lawsuit.folder)
            .where(Lawsuit.folder.is_not(None), _matches(name))
            .group_by(Lawsuit.folder)
            .order_by(func.count().desc(), Lawsuit.folder)
        )
        return [str(folder) for folder in (await self.session.execute(stmt)).scalars()]

    async def rename_matching(self, from_name: str, canonical: str) -> int:
        """Regra 3: um único UPDATE — o lote inteiro muda na mesma transação."""
        stmt = (
            update(Lawsuit)
            .where(_matches(from_name))
            .values(folder=canonical)
            .execution_options(synchronize_session=False)
        )
        result = await self.session.execute(stmt)
        return int(result.rowcount)  # type: ignore[attr-defined]

    async def folder_counts(self, limit: int) -> Sequence[FolderCount]:
        """Regra 6: contagem por pasta, decrescente; NULL (sem pasta) é um grupo."""
        stmt = (
            select(Lawsuit.folder, func.count().label("count"))
            .group_by(Lawsuit.folder)
            .order_by(func.count().desc(), Lawsuit.folder.asc().nulls_last())
            .limit(limit)
        )
        rows = await self.session.execute(stmt)
        return [
            FolderCount(name=str(name) if name is not None else None, count=int(count))
            for name, count in rows
        ]

    async def first_items_per_folder(self, per_group: int) -> Sequence[FolderGroupItem]:
        windowed = (
            select(
                Lawsuit.id,
                Lawsuit.process_number,
                Lawsuit.folder,
                Lawsuit.is_archived,
                Lawsuit.created_at,
                func.row_number()
                .over(
                    partition_by=Lawsuit.folder,
                    order_by=(Lawsuit.created_at.desc(), Lawsuit.id),
                )
                .label("rn"),
            )
        ).subquery()
        stmt = select(
            windowed.c.id,
            windowed.c.process_number,
            windowed.c.folder,
            windowed.c.is_archived,
            windowed.c.created_at,
        ).where(windowed.c.rn <= per_group)
        rows = await self.session.execute(stmt)
        return [
            FolderGroupItem(
                id=row.id,
                process_number=row.process_number,
                folder=row.folder,
                is_archived=row.is_archived,
                created_at=row.created_at,
            )
            for row in rows
        ]


def _matches(name: str) -> ColumnElement[bool]:
    return _normalized(Lawsuit.folder) == func.immutable_unaccent(func.lower(name))


class FolderService:
    def __init__(self, session: AsyncSession) -> None:
        self.folders = FolderRepository(session)

    async def search(self, *, query: str | None, limit: int) -> Sequence[FolderCount]:
        return await self.folders.search(query, limit)

    async def rename(self, *, from_name: str, to_name: str, merge: bool) -> FolderRenameResult:
        if await self.folders.count_matching(from_name) == 0:
            raise FolderNotFoundError
        if await self.folders.is_same_normalized(from_name, to_name):
            # Mesmo "nome lógico" com grafia diferente (case/acento): regrava a grafia,
            # não é fusão e não pede confirmação.
            updated = await self.folders.rename_matching(from_name, to_name)
            return FolderRenameResult(folder=to_name, updated=updated, merged=False)
        targets = await self.folders.distinct_matching(to_name)
        if targets and not merge:
            # Regra 4: fundir com pasta existente exige confirmação explícita.
            raise FolderMergeNotConfirmedError(target=targets[0])
        # Na fusão, prevalece a grafia já usada pelo alvo (a digitada, se casar exato).
        canonical = to_name if to_name in targets else (targets[0] if targets else to_name)
        updated = await self.folders.rename_matching(from_name, canonical)
        return FolderRenameResult(folder=canonical, updated=updated, merged=bool(targets))

    async def group_by_folder(self) -> Sequence[FolderGroup]:
        counts = await self.folders.folder_counts(MAX_GROUPS)
        items_by_folder: dict[str | None, list[FolderGroupItem]] = {}
        if counts:
            for item in await self.folders.first_items_per_folder(ITEMS_PER_GROUP):
                items_by_folder.setdefault(item.folder, []).append(item)
        return [
            FolderGroup(
                name=entry.name if entry.name is not None else NO_FOLDER_LABEL,
                count=entry.count,
                items=items_by_folder.get(entry.name, []),
            )
            for entry in counts
        ]
