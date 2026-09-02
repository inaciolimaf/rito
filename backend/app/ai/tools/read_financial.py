"""Ferramentas financeiras (spec 083, regra 2).

Todas exigem `financial_access >= READ_ONLY` **do usuário** — o agente não tem
privilégio próprio. Sem acesso, o registry nem oferece a ferramenta ao modelo, e uma
chamada forçada volta como erro tipado que o agente explica em português.
"""

import uuid
from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from app.ai.tools.base import MAX_ROWS, ToolContext, ToolError, tool, truncate_rows
from app.core.permissions import FinancialAccess
from app.domain.financial.dashboard import get_dashboard_stats
from app.domain.financial.models import TransactionKind
from app.domain.financial.schemas import TransactionListParams, TransactionRow
from app.domain.financial.service import TransactionService
from app.domain.lawsuits.repository import LawsuitRepository
from app.domain.lawsuits.service import LawsuitService


class SearchTransactionsInput(BaseModel):
    kind: TransactionKind | None = Field(default=None, description="RECEITA | DESPESA")
    status: str | None = Field(default=None, description="aberto | pago | atrasado")
    customer_id: uuid.UUID | None = None
    lawsuit_id: uuid.UUID | None = None
    due_from: date | None = None
    due_to: date | None = None
    query: str | None = None
    limit: int = Field(default=20, ge=1, le=MAX_ROWS)


class FinancialSummaryInput(BaseModel):
    month: date | None = Field(default=None, description="Qualquer dia do mês; padrão: mês atual.")
    regime: str = Field(default="due", description="due | payment | competence | cash_flow")


class LawsuitFinancialsInput(BaseModel):
    lawsuit_id: uuid.UUID


def _transaction_row(row: TransactionRow) -> dict[str, Any]:
    """Um lançamento como o modelo o enxerga.

    `payment_date` nulo é o que distingue previsto de realizado, e é por isso que ele vai
    explícito como `None` em vez de ser omitido: chave ausente faria o modelo tratar o
    lançamento como se a informação não existisse, e não como «ainda não foi pago».
    """
    t = row.transaction
    return {
        "id": str(t.id),
        "kind": t.kind.value,
        "amount": float(t.amount),
        "due_date": t.due_date.isoformat(),
        "payment_date": t.payment_date.isoformat() if t.payment_date else None,
        "description": t.description,
        "customer": row.customer_name,
        "category": row.category_name,
    }


@tool(
    name="search_transactions",
    description=(
        "Lançamentos financeiros por tipo, situação, cliente, processo ou vencimento. "
        "Use para 'quanto está em aberto', 'o que vence este mês'."
    ),
    requires_financial=FinancialAccess.READ_ONLY,
)
async def search_transactions(ctx: ToolContext, params: SearchTransactionsInput) -> dict[str, Any]:
    service = TransactionService(session=ctx.session, tenant_id=ctx.tenant_id)
    # Spec 098, regra 3: a listagem pagina. A ferramenta pede uma página do tamanho do
    # limite que ela mesma aplicaria — antes ela recebia a base inteira do escritório
    # para descartar tudo menos as primeiras linhas.
    rows, _cursor = await service.list_transactions(
        TransactionListParams(
            kind=params.kind,
            customer_id=params.customer_id,
            lawsuit_id=params.lawsuit_id,
            status_=params.status,
            due_from=params.due_from,
            due_to=params.due_to,
            q=params.query,
        ),
        limit=params.limit + 1,
    )
    items, truncated = truncate_rows(rows, params.limit)
    return {
        "items": [_transaction_row(row) for row in items],
        "total": len(rows),
        "truncated": truncated,
    }


@tool(
    name="get_financial_summary",
    description=(
        "Painel financeiro do mês: previsto, realizado, saldo e atrasados. "
        "Responde 'como está o caixa' sem listar lançamento a lançamento."
    ),
    requires_financial=FinancialAccess.READ_ONLY,
)
async def get_financial_summary(ctx: ToolContext, params: FinancialSummaryInput) -> dict[str, Any]:
    month = (params.month or await ctx.today()).replace(day=1)
    if params.regime not in ("due", "payment", "competence", "cash_flow"):
        raise ToolError("invalid_argument", "Regime inválido: use due, payment ou competence.")
    stats = await get_dashboard_stats(
        ctx.session,
        today=await ctx.today(),
        # A guarda acima já restringiu `regime` aos quatro literais do `Regime`, mas o
        # mypy não estreita um `str` por um `not in` com tupla.
        regime=params.regime,  # type: ignore[arg-type]
        month=month,
        account_id=None,
    )
    return {
        "month": month.isoformat(),
        "regime": params.regime,
        "income_expected": float(stats.income_expected),
        "income_realized": float(stats.income_realized),
        "expense_expected": float(stats.expense_expected),
        "expense_realized": float(stats.expense_realized),
        "balance": float(stats.balance),
        "balance_previous": float(stats.balance_previous),
        "overdue": float(stats.overdue),
        "staleness_hint": stats.balance_staleness_hint,
    }


@tool(
    name="get_lawsuit_financials",
    description="Honorários, despesas e saldo de UM processo.",
    requires_financial=FinancialAccess.READ_ONLY,
)
async def get_lawsuit_financials(
    ctx: ToolContext, params: LawsuitFinancialsInput
) -> dict[str, Any]:
    lawsuit = await LawsuitRepository(ctx.session).get_by_id(params.lawsuit_id)
    if lawsuit is None:
        raise ToolError("not_found", "Processo não encontrado neste escritório.")
    service = LawsuitService(session=ctx.session, tenant_id=ctx.tenant_id)
    summary = await service.financial_summary(lawsuit)
    return {
        "lawsuit_id": str(lawsuit.id),
        "case_value": float(lawsuit.case_value) if lawsuit.case_value else None,
        "fees_value": float(lawsuit.fees_value) if lawsuit.fees_value else None,
        "received": float(summary.received),
        "to_receive": float(summary.to_receive),
        "expenses": float(summary.expenses),
        "net_result": float(summary.net_result),
    }
