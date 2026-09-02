import uuid
from collections.abc import Mapping
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_messaging_channels
from app.core.http import get_or_404
from app.core.permissions import FinancialAccess, require_financial
from app.domain.auth.deps import get_session_for_current_user
from app.domain.dunning.exceptions import CustomerRequiredError, TransactionNotEligibleError
from app.domain.dunning.models import DunningAttempt
from app.domain.dunning.schemas import (
    AgingBucket,
    AgingBucketResponse,
    DebtorResponse,
    DunningAttemptListResponse,
    DunningAttemptResponse,
    DunningRuleListResponse,
    DunningRuleResponse,
    DunningRuleUpsertRequest,
    OverdueListResponse,
    OverdueRow,
    OverdueSummaryResponse,
    OverdueTransactionResponse,
    SendDunningRequest,
)
from app.domain.dunning.service import DunningRuleService, DunningService
from app.domain.users.models import User
from app.integrations.messaging.base import MessagingChannel

router = APIRouter(tags=["dunning"])

_AGING_BUCKETS: tuple[AgingBucket, ...] = ("1-15", "16-30", "31-60", "61-90", "90+")


def _overdue_to_response(row: OverdueRow, *, today: date) -> OverdueTransactionResponse:
    transaction = row.transaction
    return OverdueTransactionResponse(
        id=transaction.id,
        customer_id=transaction.customer_id,
        customer_name=row.customer_name,
        lawsuit_id=transaction.lawsuit_id,
        process_number=row.process_number,
        description=transaction.description,
        amount=transaction.amount,
        due_date=transaction.due_date,
        days_overdue=(today - transaction.due_date).days,
    )


def _attempt_to_response(attempt: DunningAttempt) -> DunningAttemptResponse:
    return DunningAttemptResponse(
        id=attempt.id,
        transaction_id=attempt.transaction_id,
        rule_id=attempt.rule_id,
        is_manual=attempt.rule_id is None,
        channel=attempt.channel,
        sent_to=attempt.sent_to,
        status=attempt.status,
        error=attempt.error,
        sent_at=attempt.sent_at,
    )


@router.get("/transactions/overdue")
async def list_overdue(
    aging: AgingBucket | None = Query(default=None),
    customer_id: uuid.UUID | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_financial(FinancialAccess.READ_ONLY)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> OverdueListResponse:
    if aging is not None and aging not in _AGING_BUCKETS:
        raise HTTPException(status_code=422, detail="Faixa de aging inválida.")
    service = DunningService(session=session, tenant_id=current_user.tenant_id, channels={})
    today = date.today()
    rows, next_cursor, total = await service.list_overdue(
        today=today, aging=aging, customer_id=customer_id, cursor=cursor, limit=limit
    )
    return OverdueListResponse(
        items=[_overdue_to_response(row, today=today) for row in rows],
        next_cursor=next_cursor,
        total=total,
    )


@router.get("/transactions/overdue/summary")
async def get_overdue_summary(
    current_user: User = Depends(require_financial(FinancialAccess.READ_ONLY)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> OverdueSummaryResponse:
    service = DunningService(session=session, tenant_id=current_user.tenant_id, channels={})
    summary = await service.summary(today=date.today())
    return OverdueSummaryResponse(
        total=summary.total,
        by_aging=[
            AgingBucketResponse(bucket=bucket, total=summary.by_aging[bucket])
            for bucket in _AGING_BUCKETS
        ],
        top_debtors=[
            DebtorResponse(
                customer_id=debtor.customer_id,
                customer_name=debtor.customer_name,
                total=debtor.total,
            )
            for debtor in summary.top_debtors
        ],
    )


@router.get("/dunning-rules")
async def list_dunning_rules(
    current_user: User = Depends(require_financial(FinancialAccess.FULL)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> DunningRuleListResponse:
    service = DunningRuleService(session=session, tenant_id=current_user.tenant_id)
    rules = await service.list_rules()
    return DunningRuleListResponse(
        items=[
            DunningRuleResponse(
                id=rule.id,
                days_offset=rule.days_offset,
                channel=rule.channel,
                template=rule.template,
                is_active=rule.is_active,
                created_at=rule.created_at,
            )
            for rule in rules
        ]
    )


@router.put("/dunning-rules")
async def upsert_dunning_rule(
    payload: DunningRuleUpsertRequest,
    current_user: User = Depends(require_financial(FinancialAccess.FULL)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> DunningRuleResponse:
    service = DunningRuleService(session=session, tenant_id=current_user.tenant_id)
    rule = await service.upsert(payload)
    return DunningRuleResponse(
        id=rule.id,
        days_offset=rule.days_offset,
        channel=rule.channel,
        template=rule.template,
        is_active=rule.is_active,
        created_at=rule.created_at,
    )


@router.post("/transactions/{transaction_id}/dunning/send")
async def send_dunning(
    transaction_id: uuid.UUID,
    payload: SendDunningRequest,
    current_user: User = Depends(require_financial(FinancialAccess.FULL)),
    session: AsyncSession = Depends(get_session_for_current_user),
    channels: Mapping[str, MessagingChannel] = Depends(get_messaging_channels),
) -> DunningAttemptResponse:
    service = DunningService(session=session, tenant_id=current_user.tenant_id, channels=channels)
    row = await get_or_404(
        lambda: service.get_overdue(transaction_id), "Lançamento não encontrado."
    )
    try:
        attempt = await service.send_manual(
            row, channel=payload.channel, template=payload.template, today=date.today()
        )
    except TransactionNotEligibleError as exc:
        raise HTTPException(
            status_code=422,
            detail="Lançamento não é uma receita em aberto — nada para cobrar.",
        ) from exc
    except CustomerRequiredError as exc:
        raise HTTPException(status_code=422, detail="Lançamento sem cliente vinculado.") from exc
    return _attempt_to_response(attempt)


@router.get("/transactions/{transaction_id}/dunning/attempts")
async def list_dunning_attempts(
    transaction_id: uuid.UUID,
    current_user: User = Depends(require_financial(FinancialAccess.READ_ONLY)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> DunningAttemptListResponse:
    service = DunningService(session=session, tenant_id=current_user.tenant_id, channels={})
    await get_or_404(lambda: service.get_overdue(transaction_id), "Lançamento não encontrado.")
    attempts = await service.list_attempts(transaction_id)
    return DunningAttemptListResponse(items=[_attempt_to_response(a) for a in attempts])
