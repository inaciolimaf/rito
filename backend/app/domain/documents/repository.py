import uuid
from collections.abc import Sequence

from sqlalchemy import func, select

from app.core.repository import BaseRepository
from app.domain.documents.models import Document, DocumentFolder, DocumentScopeType
from app.domain.documents.schemas import SortField, SortOrder

_DOCUMENT_SORT_COLUMNS = {
    "name": Document.filename,
    "created_at": Document.created_at,
    "size_bytes": Document.size_bytes,
    "content_type": Document.content_type,
}


class DocumentFolderRepository(BaseRepository[DocumentFolder]):
    model = DocumentFolder

    async def get_by_name(
        self,
        *,
        scope_type: DocumentScopeType,
        scope_id: uuid.UUID,
        parent_folder_id: uuid.UUID | None,
        name: str,
    ) -> DocumentFolder | None:
        parent_condition = (
            DocumentFolder.parent_folder_id == parent_folder_id
            if parent_folder_id is not None
            else DocumentFolder.parent_folder_id.is_(None)
        )
        stmt = select(DocumentFolder).where(
            DocumentFolder.scope_type == scope_type,
            DocumentFolder.scope_id == scope_id,
            parent_condition,
            DocumentFolder.name == name,
        )
        result = await self.session.scalars(stmt)
        return result.first()

    async def list_in(
        self,
        *,
        scope_type: DocumentScopeType,
        scope_id: uuid.UUID,
        parent_folder_id: uuid.UUID | None,
    ) -> Sequence[DocumentFolder]:
        parent_condition = (
            DocumentFolder.parent_folder_id == parent_folder_id
            if parent_folder_id is not None
            else DocumentFolder.parent_folder_id.is_(None)
        )
        stmt = (
            select(DocumentFolder)
            .where(
                DocumentFolder.scope_type == scope_type,
                DocumentFolder.scope_id == scope_id,
                parent_condition,
            )
            .order_by(DocumentFolder.name)
        )
        return (await self.session.scalars(stmt)).all()

    async def list_children(self, parent_folder_id: uuid.UUID) -> Sequence[DocumentFolder]:
        stmt = select(DocumentFolder).where(DocumentFolder.parent_folder_id == parent_folder_id)
        return (await self.session.scalars(stmt)).all()

    async def descendant_ids(self, folder_id: uuid.UUID) -> list[uuid.UUID]:
        """Regra 4 (cascata): junta o próprio id com o de toda subpasta, em Python —
        a árvore de pastas de um único escopo é rasa o bastante (uso real de
        escritório) pra não precisar de uma CTE recursiva no banco."""
        ids = [folder_id]
        pending = [folder_id]
        while pending:
            current = pending.pop()
            children = await self.list_children(current)
            for child in children:
                ids.append(child.id)
                pending.append(child.id)
        return ids


class DocumentRepository(BaseRepository[Document]):
    model = Document

    async def list_in(
        self,
        *,
        scope_type: DocumentScopeType,
        scope_id: uuid.UUID,
        folder_id: uuid.UUID | None,
        sort: SortField,
        order: SortOrder,
    ) -> Sequence[Document]:
        column = _DOCUMENT_SORT_COLUMNS[sort]
        ordered = column.desc() if order == "desc" else column.asc()
        folder_condition = (
            Document.folder_id == folder_id
            if folder_id is not None
            else Document.folder_id.is_(None)
        )
        stmt = (
            select(Document)
            .where(
                Document.scope_type == scope_type, Document.scope_id == scope_id, folder_condition
            )
            .order_by(ordered, Document.id)
        )
        return (await self.session.scalars(stmt)).all()

    async def list_in_folders(self, folder_ids: Sequence[uuid.UUID]) -> Sequence[Document]:
        if not folder_ids:
            return []
        stmt = select(Document).where(Document.folder_id.in_(folder_ids))
        return (await self.session.scalars(stmt)).all()

    async def search(
        self, *, scope_type: DocumentScopeType, scope_id: uuid.UUID, query: str
    ) -> Sequence[Document]:
        stmt = (
            select(Document)
            .where(
                Document.scope_type == scope_type,
                Document.scope_id == scope_id,
                Document.filename.ilike(f"%{query}%"),
            )
            .order_by(Document.filename)
        )
        return (await self.session.scalars(stmt)).all()

    async def total_size_bytes(self) -> int:
        """Regra 5: soma de TODO documento do tenant (todo escopo) — RLS já garante
        que só as linhas do tenant atual entram na soma (CLAUDE.md §4)."""
        value = await self.session.scalar(select(func.coalesce(func.sum(Document.size_bytes), 0)))
        return int(value or 0)
