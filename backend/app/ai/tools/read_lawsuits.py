"""Ferramentas de leitura de processos e intimações (spec 083)."""

import uuid
from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from app.ai.tools.base import MAX_ROWS, ToolContext, ToolError, tool, truncate_rows
from app.domain.lawsuits.parties_service import PartiesService
from app.domain.lawsuits.schemas import LawsuitFiltersQuery
from app.domain.lawsuits.service import LawsuitService
from app.domain.publications.schemas import PublicationFilters
from app.domain.publications.service import PublicationService

# Tipos da timeline unificada (spec 026) — o padrão traz tudo.
_ALL_TIMELINE_KINDS = ("movement", "post", "publication", "document", "stage")


class SearchLawsuitsInput(BaseModel):
    query: str | None = Field(default=None, description="Número, pasta, parte ou observação.")
    customer_id: uuid.UUID | None = None
    stage_id: uuid.UUID | None = None
    responsible_id: uuid.UUID | None = Field(default=None, description="Advogado responsável.")
    process_number: str | None = None
    limit: int = Field(default=20, ge=1, le=MAX_ROWS)


class GetLawsuitInput(BaseModel):
    lawsuit_id: uuid.UUID


class GetTimelineInput(BaseModel):
    lawsuit_id: uuid.UUID
    limit: int = Field(default=20, ge=1, le=MAX_ROWS)


class SearchPublicationsInput(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    court_code: str | None = None
    process_number: str | None = None
    only_unread: bool = False
    limit: int = Field(default=20, ge=1, le=MAX_ROWS)


class GetPublicationInput(BaseModel):
    publication_id: uuid.UUID


def _lawsuit_summary(row: Any) -> dict[str, Any]:
    lawsuit = row.lawsuit
    return {
        "id": str(lawsuit.id),
        "process_number": lawsuit.process_number,
        "folder": lawsuit.folder,
        "action_group": row.action_group_name,
        "lawsuit_type": row.lawsuit_type_name,
        "stage": row.stage_name,
        "parties": row.parties,
        "last_movement": row.last_movement_title,
        "is_archived": lawsuit.is_archived,
    }


@tool(
    name="search_lawsuits",
    description=(
        "Busca processos por número, pasta, parte, fase ou responsável. "
        "Use para responder 'quais processos...' e para achar o id de um processo."
    ),
)
async def search_lawsuits(ctx: ToolContext, params: SearchLawsuitsInput) -> dict[str, Any]:
    service = LawsuitService(session=ctx.session, tenant_id=ctx.tenant_id)
    rows, _cursor, total = await service.list_lawsuits(
        payload=LawsuitFiltersQuery(
            q=params.query,
            customer_id=params.customer_id,
            stage_id=str(params.stage_id) if params.stage_id else None,
            user_id=str(params.responsible_id) if params.responsible_id else None,
            process_number=params.process_number,
        ),
        order="desc",
        cursor=None,
        limit=min(params.limit, MAX_ROWS),
    )
    items, truncated = truncate_rows(rows, params.limit)
    return {
        "items": [_lawsuit_summary(row) for row in items],
        "total": total,
        "truncated": truncated or total > len(items),
    }


@tool(
    name="get_lawsuit",
    description="Processo completo: dados, partes, fase, valores e datas do ciclo de vida.",
)
async def get_lawsuit(ctx: ToolContext, params: GetLawsuitInput) -> dict[str, Any]:
    service = LawsuitService(session=ctx.session, tenant_id=ctx.tenant_id)
    detail = await service.get(params.lawsuit_id)
    if detail is None:
        raise ToolError("not_found", "Processo não encontrado neste escritório.")
    lawsuit = detail.lawsuit
    parties = await PartiesService(session=ctx.session, tenant_id=ctx.tenant_id).list_parties(
        lawsuit.id
    )
    # Regra 2 da 083 + regra 9 da 079: valor é dado financeiro; sem acesso, não sai.
    from app.core.permissions import FinancialAccess

    can_see_money = ctx.user.financial_access != FinancialAccess.NONE
    return {
        "id": str(lawsuit.id),
        "process_number": lawsuit.process_number,
        "folder": lawsuit.folder,
        "action_group": detail.action_group_name,
        "step": detail.step_name,
        "parties": [
            {
                "name": party.customer_name,
                "pole": party.party.pole.value,
                "is_client": party.party.is_client,
            }
            for party in parties
        ],
        "county": lawsuit.county,
        "judiciary": lawsuit.judiciary,
        "notes": lawsuit.notes,
        "case_value": float(lawsuit.case_value) if can_see_money and lawsuit.case_value else None,
        "fees_value": float(lawsuit.fees_value) if can_see_money and lawsuit.fees_value else None,
        "closure_date": lawsuit.closure_date.isoformat() if lawsuit.closure_date else None,
        "archived_date": lawsuit.archived_date.isoformat() if lawsuit.archived_date else None,
        "outcome": lawsuit.outcome.value if lawsuit.outcome else None,
        "financial_redacted": not can_see_money,
    }


@tool(
    name="get_lawsuit_timeline",
    description=(
        "Timeline unificada de um processo: movimentações, tarefas, intimações e "
        "documentos, do mais recente para o mais antigo."
    ),
)
async def get_lawsuit_timeline(ctx: ToolContext, params: GetTimelineInput) -> dict[str, Any]:
    service = LawsuitService(session=ctx.session, tenant_id=ctx.tenant_id)
    if await service.get(params.lawsuit_id) is None:
        raise ToolError("not_found", "Processo não encontrado neste escritório.")
    page = await service.list_timeline(
        params.lawsuit_id,
        kinds=_ALL_TIMELINE_KINDS,
        cursor=None,
        limit=min(params.limit, MAX_ROWS),
    )
    return {
        "items": [
            {
                "kind": item.kind,
                "occurred_at": item.occurred_at.isoformat(),
                "title": item.title,
                "summary": item.summary,
                "actor": item.actor,
            }
            for item in page.items
        ],
        "truncated": page.next_cursor is not None,
    }


@tool(
    name="search_publications",
    description=(
        "Busca intimações recebidas por período, tribunal ou processo. "
        "Use `only_unread` para o que ainda não foi lido."
    ),
)
async def search_publications(ctx: ToolContext, params: SearchPublicationsInput) -> dict[str, Any]:
    service = PublicationService(session=ctx.session, tenant_id=ctx.tenant_id)
    filters = PublicationFilters(
        interval="custom" if params.date_from and params.date_to else "7d",
        date_from=params.date_from,
        date_to=params.date_to,
        court_code=params.court_code,
        process_number=params.process_number,
        read=False if params.only_unread else None,
    )
    rows, _cursor, total = await service.list_publications(
        filters=filters,
        current_user_id=ctx.user.id,
        cursor=None,
        limit=min(params.limit, MAX_ROWS),
        today=await ctx.today(),
    )
    items, truncated = truncate_rows(rows, params.limit)
    return {
        "items": [
            {
                "id": str(row.publication.id),
                "availability_date": row.publication.availability_date.isoformat(),
                "court": row.publication.court_code,
                "process_number": row.publication.process_number,
                "kind": row.publication.communication_type,
                "is_read": row.is_read,
                "lawsuit_id": (
                    str(row.publication.lawsuit_id) if row.publication.lawsuit_id else None
                ),
            }
            for row in items
        ],
        "total": total,
        "truncated": truncated or total > len(items),
    }


@tool(
    name="get_publication",
    description="Inteiro teor de uma intimação, com destinatários e advogados citados.",
)
async def get_publication(ctx: ToolContext, params: GetPublicationInput) -> dict[str, Any]:
    service = PublicationService(session=ctx.session, tenant_id=ctx.tenant_id)
    publication = await service.get_by_id(params.publication_id)
    if publication is None:
        raise ToolError("not_found", "Intimação não encontrada neste escritório.")
    detail = await service.get_detail(publication, current_user_id=ctx.user.id)
    return {
        "id": str(publication.id),
        "availability_date": publication.availability_date.isoformat(),
        "court": publication.court_code,
        "process_number": publication.process_number,
        "kind": publication.communication_type,
        "body": publication.body,
        "is_read": detail.is_read,
        "recipients": [item.name for item in detail.recipients],
        "lawyers": [item.name for item in detail.lawyers],
    }
