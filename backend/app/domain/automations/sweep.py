"""Varreduras do motor (spec 092).

Dois gatilhos não nascem de uma escrita: `transaction.overdue` é uma DATA que passou, e
uma execução esperando N dias precisa de alguém que a acorde. A regra em si mora aqui, no
domínio, e o worker (`app/workers/automations.py`) só a chama por tenant — mesmo padrão da
régua de cobrança da 061: assim o teste exercita a regra sem subir fila (CLAUDE.md §3).
"""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.automations.engine import AutomationEngine
from app.domain.automations.models import TriggerKind
from app.domain.financial.models import Transaction


async def emit_overdue_transactions(
    session: AsyncSession, tenant_id: uuid.UUID, *, today: date
) -> int:
    """Lançamentos que venceram HOJE viram gatilho — uma vez, no dia.

    A janela é o dia exato de propósito: varrer "tudo que está vencido" republicaria o
    mesmo lançamento todo dia, e a automação de cobrança dispararia de novo a cada
    varredura. Um lançamento vence uma vez.
    """
    # "Vencido" aqui é o mesmo de todo o financeiro: venceu e não foi pago
    # (`payment_date IS NULL`). Lançamento de controle fica de fora, como em qualquer
    # cálculo que envolva dinheiro de verdade (spec 058, regra 1).
    stmt = select(Transaction).where(
        Transaction.due_date == today,
        Transaction.payment_date.is_(None),
        Transaction.is_internal.is_(False),
    )
    vencidos = list((await session.scalars(stmt)).all())
    engine = AutomationEngine(session, tenant_id)
    for transaction in vencidos:
        await engine.emit(
            TriggerKind.TRANSACTION_OVERDUE.value,
            payload={
                "transaction_id": str(transaction.id),
                "lawsuit_id": str(transaction.lawsuit_id) if transaction.lawsuit_id else None,
                "customer_id": str(transaction.customer_id) if transaction.customer_id else None,
                "amount": str(transaction.amount),
                "due_date": transaction.due_date.isoformat(),
            },
            subject_type="transaction",
            subject_id=transaction.id,
        )
    return len(vencidos)


async def resume_due_runs(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    return await AutomationEngine(session, tenant_id).resume_due()
