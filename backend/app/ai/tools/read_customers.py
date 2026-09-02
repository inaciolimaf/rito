"""Ferramentas de leitura de contatos (spec 083).

Todas escritas sobre os services de domínio (regra 10): a ferramenta não sabe SQL, sabe
pedir para o `CustomerService` — que já carrega filtro, ordenação, paginação e RLS.
"""

import uuid
from typing import Any

from pydantic import BaseModel, Field

from app.ai.tools.base import MAX_ROWS, ToolContext, ToolError, tool, truncate_rows
from app.domain.customers.schemas import CustomerFilters
from app.domain.customers.service import CustomerService
from app.domain.lawsuits.schemas import LawsuitFiltersQuery
from app.domain.lawsuits.service import LawsuitService


class SearchCustomersInput(BaseModel):
    query: str | None = Field(default=None, description="Nome, CPF/CNPJ ou e-mail.")
    city: str | None = None
    state: str | None = Field(default=None, description="UF com 2 letras.")
    origin_id: uuid.UUID | None = None
    limit: int = Field(default=20, ge=1, le=MAX_ROWS)


class GetCustomerInput(BaseModel):
    customer_id: uuid.UUID


def _customer_summary(customer: Any) -> dict[str, Any]:
    return {
        "id": str(customer.id),
        "name": customer.name,
        "type": customer.type.value if hasattr(customer.type, "value") else customer.type,
        "identification": customer.identification,
        "city": customer.city,
        "state": customer.state,
        "email": customer.email,
        "cellphone": customer.cellphone,
    }


@tool(
    name="search_customers",
    description=(
        "Busca contatos do escritório por nome, CPF/CNPJ, cidade, UF ou origem. "
        "Use quando o usuário citar uma pessoa ou empresa pelo nome."
    ),
)
async def search_customers(ctx: ToolContext, params: SearchCustomersInput) -> dict[str, Any]:
    service = CustomerService(session=ctx.session, tenant_id=ctx.tenant_id)
    items, _cursor, total = await service.list_customers(
        today=await ctx.today(),
        filters=CustomerFilters(
            q=params.query, city=params.city, state=params.state, origin_id=params.origin_id
        ),
        sort="name",
        order="asc",
        cursor=None,
        limit=min(params.limit, MAX_ROWS),
    )
    rows, truncated = truncate_rows(items, params.limit)
    return {
        "items": [_customer_summary(row) for row in rows],
        "total": total,
        "truncated": truncated or total > len(rows),
    }


@tool(
    name="get_customer",
    description=(
        "Ficha completa de um contato, com os processos em que ele é parte. "
        "Exige o id do contato — use search_customers antes se só tiver o nome."
    ),
)
async def get_customer(ctx: ToolContext, params: GetCustomerInput) -> dict[str, Any]:
    service = CustomerService(session=ctx.session, tenant_id=ctx.tenant_id)
    customer = await service.get(params.customer_id)
    if customer is None:
        raise ToolError("not_found", "Contato não encontrado neste escritório.")

    lawsuits = LawsuitService(session=ctx.session, tenant_id=ctx.tenant_id)
    rows, _cursor, total = await lawsuits.list_lawsuits(
        payload=LawsuitFiltersQuery(customer_id=customer.id),
        order="desc",
        cursor=None,
        limit=20,
    )
    return {
        "customer": {
            **_customer_summary(customer),
            "birthdate": customer.birthdate.isoformat() if customer.birthdate else None,
            "occupation": customer.occupation,
            "street": customer.street,
            "notes": customer.notes,
        },
        "lawsuits": [
            {
                "id": str(row.lawsuit.id),
                "process_number": row.lawsuit.process_number,
                "folder": row.lawsuit.folder,
                "stage_name": row.stage_name,
            }
            for row in rows
        ],
        "lawsuits_total": total,
    }
