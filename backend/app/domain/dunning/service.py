import logging
import uuid
from collections.abc import Mapping, Sequence
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Tenant
from app.core.repository import decode_cursor, encode_cursor
from app.domain.dunning.exceptions import CustomerRequiredError, TransactionNotEligibleError
from app.domain.dunning.models import DunningAttempt, DunningChannel, DunningRule, DunningStatus
from app.domain.dunning.repository import (
    DunningAttemptRepository,
    DunningRuleRepository,
    OverdueRepository,
)
from app.domain.dunning.schemas import (
    AgingBucket,
    DunningRuleUpsertRequest,
    OverdueRow,
    OverdueSummary,
)
from app.domain.dunning.template import TemplateContext, render_template
from app.domain.financial.models import TransactionKind
from app.integrations.messaging.base import ChannelNotConfiguredError, MessagingChannel

logger = logging.getLogger(__name__)


class DunningRuleService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.rules = DunningRuleRepository(session)

    async def list_rules(self) -> Sequence[DunningRule]:
        return await self.rules.list_all()

    async def upsert(self, payload: DunningRuleUpsertRequest) -> DunningRule:
        """`PUT /dunning-rules` (spec 061 §5) — upsert por `(days_offset, channel)`,
        que é a UNIQUE da migration: já existe → atualiza template/is_active; senão,
        cria. Não há `DELETE` no contrato — desativar é sempre via `is_active=false`."""
        existing = await self.rules.get_by_offset_channel(
            days_offset=payload.days_offset, channel=payload.channel
        )
        if existing is not None:
            existing.template = payload.template
            existing.is_active = payload.is_active
            return existing
        rule = DunningRule(
            tenant_id=self.tenant_id,
            days_offset=payload.days_offset,
            channel=payload.channel,
            template=payload.template,
            is_active=payload.is_active,
        )
        return await self.rules.create(rule)


class DunningService:
    """Envio de cobrança (spec 061) — manual (regra 8) e disparado pela régua diária
    (regra 3/10). `channels` é o registro de `MessagingChannel` por nome (regra 9:
    e-mail real, SMS/WhatsApp sempre `ChannelNotConfiguredError`)."""

    def __init__(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        channels: Mapping[str, MessagingChannel],
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.channels = channels
        self.overdue = OverdueRepository(session)
        self.attempts = DunningAttemptRepository(session)
        self.rules = DunningRuleRepository(session)

    async def get_overdue(self, transaction_id: uuid.UUID) -> OverdueRow | None:
        return await self.overdue.get_by_transaction_id(transaction_id)

    async def list_overdue(
        self,
        *,
        today: date,
        aging: AgingBucket | None,
        customer_id: uuid.UUID | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[Sequence[OverdueRow], str | None, int]:
        """Página de vencidos, no formato do contrato de listagem (CLAUDE.md §6).

        O codec de cursor vinha rodando no router (spec 118, checagem 2). Ele é da
        camada de dados — quem sabe por qual valor a página ordena é quem ordena —, e o
        router agora só repassa a string opaca que recebeu na query string.
        """
        decoded: tuple[date, uuid.UUID] | None = None
        if cursor:
            sort_value, cursor_id = decode_cursor(cursor)
            decoded = (date.fromisoformat(sort_value), cursor_id)

        rows, total = await self.overdue.list_overdue(
            today=today, aging=aging, customer_id=customer_id, cursor=decoded, limit=limit
        )

        next_cursor = None
        if len(rows) == limit:
            last = rows[-1].transaction
            next_cursor = encode_cursor(last.due_date.isoformat(), last.id)
        return rows, next_cursor, total

    async def summary(self, *, today: date) -> OverdueSummary:
        return await self.overdue.summary(today=today)

    async def list_attempts(self, transaction_id: uuid.UUID) -> Sequence[DunningAttempt]:
        return await self.attempts.list_for_transaction(transaction_id)

    async def send_manual(
        self, row: OverdueRow, *, channel: DunningChannel, template: str, today: date
    ) -> DunningAttempt:
        """Regra 8: sempre permitido, mesmo que a régua já tenha rodado — `rule_id`
        fica `NULL`, o que também é o que marca a tentativa como manual (nunca colide
        com a UNIQUE de `(transaction_id, rule_id)`, já que Postgres trata NULL como
        distinto)."""
        transaction = row.transaction
        if (
            transaction.kind != TransactionKind.RECEITA
            or transaction.payment_date is not None
            or transaction.is_internal
        ):
            raise TransactionNotEligibleError
        if transaction.customer_id is None:
            raise CustomerRequiredError
        return await self._attempt_send(
            row, channel=channel, rule_id=None, template=template, today=today
        )

    async def run_daily_rules(self, reference_date: date) -> int:
        """Regra 3/10: worker diário. Para cada régua ativa, o alvo é `due_date =
        reference_date - days_offset` — offset negativo (lembrete) aponta pra uma data
        FUTURA em relação a hoje, positivo (cobrança) pra uma PASSADA. Uma falha num
        lançamento não pode derrubar os outros nem as outras réguas."""
        sent = 0
        for rule in await self.rules.list_active():
            target_due_date = reference_date - timedelta(days=rule.days_offset)
            rows = await self.overdue.list_due_for_rule(target_due_date=target_due_date)
            for row in rows:
                try:
                    already_sent = await self.attempts.exists_for_rule(
                        transaction_id=row.transaction.id, rule_id=rule.id
                    )
                    if already_sent:  # regra 4
                        continue
                    await self._attempt_send(
                        row,
                        channel=rule.channel,
                        rule_id=rule.id,
                        template=rule.template,
                        today=reference_date,
                    )
                    sent += 1
                except Exception:  # regra 10: um lançamento ruim não para o lote
                    logger.exception(
                        "dunning: falha inesperada no lançamento %s (régua %s)",
                        row.transaction.id,
                        rule.id,
                    )
        return sent

    async def _attempt_send(
        self,
        row: OverdueRow,
        *,
        channel: DunningChannel,
        rule_id: uuid.UUID | None,
        template: str,
        today: date,
    ) -> DunningAttempt:
        transaction = row.transaction
        contact = self._resolve_contact(channel, row)
        days_overdue = (today - transaction.due_date).days

        if contact is None:  # regra 5: sem contato do canal — silêncio nunca
            attempt = DunningAttempt(
                tenant_id=self.tenant_id,
                transaction_id=transaction.id,
                rule_id=rule_id,
                channel=channel,
                sent_to="",
                status=DunningStatus.SKIPPED,
                error="Cliente sem contato cadastrado para este canal.",
            )
            return await self.attempts.create(attempt)

        tenant = await self.session.get(Tenant, self.tenant_id)
        assert tenant is not None  # tenant da sessão atual sempre existe
        message = render_template(
            template,
            TemplateContext(
                customer_name=row.customer_name or "",
                amount=transaction.amount,
                due_date=transaction.due_date,
                days_overdue=days_overdue,
                process_number=row.process_number,
                tenant_name=tenant.name,
            ),
        )
        subject = "Lembrete de vencimento" if days_overdue <= 0 else "Cobrança de valor em atraso"

        status_: DunningStatus
        error: str | None
        try:
            await self.channels[channel.value].send(to=contact, subject=subject, message=message)
            status_, error = DunningStatus.SENT, None
        except ChannelNotConfiguredError as exc:  # regra 9
            status_, error = DunningStatus.SKIPPED, str(exc)
        except Exception as exc:  # falha real do provider — regra 10 protege o lote
            status_, error = DunningStatus.FAILED, str(exc)[:500]

        attempt = DunningAttempt(
            tenant_id=self.tenant_id,
            transaction_id=transaction.id,
            rule_id=rule_id,
            channel=channel,
            sent_to=contact,
            status=status_,
            error=error,
        )
        return await self.attempts.create(attempt)

    @staticmethod
    def _resolve_contact(channel: DunningChannel, row: OverdueRow) -> str | None:
        if channel == DunningChannel.EMAIL:
            return row.customer_email
        return row.customer_cellphone
