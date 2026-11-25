"""Caso de uso da tela de Atividades (spec 128).

Mora em arquivo próprio pelo mesmo critério que separou `creation.py`, `completion.py` e
`detail.py` de `service.py` na spec 040: um caso de uso, uma unidade. O `PostService` é
sobre UMA tarefa (ler, editar, excluir); aqui a unidade é a lista do escritório.
"""

import uuid
from datetime import date
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.listing import Page
from app.core.repository import decode_cursor, encode_cursor
from app.domain.posts.export import build_pdf, build_xlsx
from app.domain.posts.listing import (
    EXPORT_ROW_LIMIT,
    ActivityListingRepository,
    ActivityListRow,
    Predicate,
    build_conditions,
    decode_sort_value,
    filters_from_query,
)
from app.domain.posts.schemas import ActivityFiltersQuery


def _next_cursor(rows: list[ActivityListRow], page: Page) -> str | None:
    """Página incompleta é a última — não há próxima. O valor codificado é o de
    ordenação JÁ coalescido (a linha o traz de volta da query), senão uma tarefa sem data
    geraria um cursor que ela mesma não satisfaz."""
    if len(rows) < page.limit:
        return None
    ultima = rows[-1]
    return encode_cursor(ultima.sort_value.isoformat(), ultima.post.id)


def _page_from_query(*, sort: str, order: str, cursor: str | None, limit: int) -> Page:
    """Os quatro parâmetros de paginação do §6, com o valor do cursor já no tipo da
    coluna de ordenação."""
    decodificado = None
    if cursor:
        valor, cursor_id = decode_cursor(cursor)
        decodificado = (decode_sort_value(sort, valor), cursor_id)
    return Page(sort=sort, descending=order == "desc", cursor=decodificado, limit=limit)


class ActivityService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.listing = ActivityListingRepository(session)

    async def list_activities(
        self,
        *,
        payload: ActivityFiltersQuery,
        viewer_id: uuid.UUID,
        today: date,
        sort: str,
        order: str,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[ActivityListRow], str | None, int]:
        """`viewer_id` fica FORA de `ActivityFilters` de propósito: não é um filtro que o
        chamador escolhe, é quem está perguntando — e é ele que decide o que a regra 8 da
        033 esconde. Misturá-lo aos filtros abriria a porta para "filtrar" por outro
        usuário e ver o que não pode (mesma decisão do `search` da 083)."""
        page = _page_from_query(sort=sort, order=order, cursor=cursor, limit=limit)
        conditions = self._conditions(payload, viewer_id=viewer_id, today=today)
        rows, total = await self.listing.list_filtered(conditions=conditions, page=page)
        return rows, _next_cursor(rows, page), total

    async def export(
        self,
        *,
        payload: ActivityFiltersQuery,
        viewer_id: uuid.UUID,
        today: date,
        sort: str,
        order: str,
        format_: Literal["xlsx", "pdf"],
    ) -> bytes:
        """Regra 7: os filtros ativos, não a página visível — mesma construção de
        condições da listagem, com o teto de linhas no lugar do `limit` da página."""
        conditions = self._conditions(payload, viewer_id=viewer_id, today=today)
        page = Page(sort=sort, descending=order == "desc", limit=EXPORT_ROW_LIMIT)
        rows, _total = await self.listing.list_filtered(conditions=conditions, page=page)
        return build_xlsx(rows, today) if format_ == "xlsx" else build_pdf(rows, today)

    @staticmethod
    def _conditions(
        payload: ActivityFiltersQuery, *, viewer_id: uuid.UUID, today: date
    ) -> list[Predicate]:
        """A tradução «query string → filtros do domínio» mora aqui, no service, porque é
        ele quem faz a ponte entre HTTP e domínio (CLAUDE.md §5) — e porque listagem e
        export TÊM que enxergar o mesmo conjunto (regra 7)."""
        return build_conditions(filters_from_query(payload), viewer_id=viewer_id, today=today)
