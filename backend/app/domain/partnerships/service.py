"""Regras da parceria (spec 079).

O service conhece duas fontes: os repositórios normais (tudo do próprio escritório,
sob RLS) e o `PartnerGateway` (o que atravessa a fronteira, sempre com escopo
verificado no banco). Nenhuma query cross-tenant é montada aqui.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Row
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tokens import generate_refresh_token, hash_token
from app.domain.lawsuits.repository import LawsuitRepository
from app.domain.partnerships.exceptions import (
    InvalidInviteError,
    InvalidTaskTypeError,
    LawsuitNotSharedError,
    PartnershipAlreadyExistsError,
    PartnershipNotFoundError,
    SharingForbiddenError,
)
from app.domain.partnerships.models import (
    Partnership,
    PartnershipStatus,
    SharedLawsuit,
)
from app.domain.partnerships.repository import (
    PartnershipAuditRepository,
    PartnershipRepository,
    SharedLawsuitRepository,
)
from app.domain.partnerships.schemas import (
    PartnerTaskCreateRequest,
    ShareLawsuitRequest,
)
from app.domain.partnerships.sharing import PartnerGateway, ShareScope
from app.domain.users.models import User

# Ações auditadas (regra 11).
ACTION_INVITE = "INVITE"
ACTION_ACCEPT = "ACCEPT"
ACTION_END = "END"
ACTION_SHARE = "SHARE"
ACTION_REVOKE = "REVOKE"
ACTION_PARTNER_TASK = "PARTNER_TASK"


@dataclass(frozen=True)
class PartnershipView:
    partnership: Partnership
    partner_name: str | None
    is_requester: bool
    shared_count: int


@dataclass(frozen=True)
class SharedLawsuitDetail:
    lawsuit: Row[Any]
    parties: Sequence[Row[Any]]
    timeline: Sequence[Row[Any]]
    tasks: Sequence[Row[Any]]


class PartnershipService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.partnerships = PartnershipRepository(session)
        self.shares = SharedLawsuitRepository(session)
        self.audit = PartnershipAuditRepository(session)
        self.lawsuits = LawsuitRepository(session)
        self.gateway = PartnerGateway(session)

    # ------------------------------------------------------------------ rede

    async def list_partnerships(
        self, *, status: PartnershipStatus | None = None
    ) -> list[PartnershipView]:
        rows = await self.partnerships.list_for_tenant(status=status)
        counts = await self.shares.counts_by_partnership()
        other_ids = {other for row in rows if (other := self._other_tenant_id(row)) is not None}
        names = await self.partnerships.tenant_names(other_ids)
        return [
            PartnershipView(
                partnership=row,
                partner_name=names.get(other) if (other := self._other_tenant_id(row)) else None,
                is_requester=row.requester_tenant_id == self.tenant_id,
                shared_count=counts.get(row.id, 0),
            )
            for row in rows
        ]

    def _other_tenant_id(self, partnership: Partnership) -> uuid.UUID | None:
        """Regra 1: a parceria é simétrica — o "parceiro" é sempre o outro lado."""
        if partnership.requester_tenant_id == self.tenant_id:
            return partnership.partner_tenant_id
        return partnership.requester_tenant_id

    async def invite(self, *, actor: User, email: str) -> tuple[PartnershipView, str, bool]:
        existing = await self.partnerships.get_by_invited_email(email)
        if existing is not None and existing.status in (
            PartnershipStatus.PENDENTE,
            PartnershipStatus.ATIVA,
        ):
            raise PartnershipAlreadyExistsError
        raw_token, token_hash = generate_refresh_token()
        partnership = Partnership(
            requester_tenant_id=self.tenant_id,
            invited_email=email,
            token_hash=token_hash,
            invited_by=actor.id,
        )
        if existing is not None:
            # Recusada/encerrada: o UNIQUE (tenant, e-mail) é por e-mail, então o convite
            # novo reaproveita a linha em vez de colidir com o histórico.
            existing.status = PartnershipStatus.PENDENTE
            existing.token_hash = token_hash
            existing.invited_by = actor.id
            existing.partner_tenant_id = None
            existing.accepted_at = None
            partnership = existing
            await self.session.flush()
        else:
            await self.partnerships.create(partnership)
        account_exists = await self.gateway.email_has_account(email)
        await self.audit.record(
            tenant_id=self.tenant_id,
            action=ACTION_INVITE,
            actor_user_id=actor.id,
            partnership_id=partnership.id,
            detail={"email": email, "account_exists": account_exists},
        )
        view = PartnershipView(
            partnership=partnership, partner_name=None, is_requester=True, shared_count=0
        )
        return view, raw_token, account_exists

    async def accept(self, *, actor: User, token: str) -> PartnershipView:
        partnership_id = await self.gateway.accept_invite(hash_token(token), str(actor.email))
        if partnership_id is None:
            raise InvalidInviteError
        await self.audit.record(
            tenant_id=self.tenant_id,
            action=ACTION_ACCEPT,
            actor_user_id=actor.id,
            partnership_id=partnership_id,
            detail={"email": str(actor.email)},
        )
        partnership = await self.partnerships.get_by_id(partnership_id)
        if partnership is None:  # pragma: no cover - o aceite acabou de tornar visível
            raise InvalidInviteError
        names = await self.partnerships.tenant_names({partnership.requester_tenant_id})
        return PartnershipView(
            partnership=partnership,
            partner_name=names.get(partnership.requester_tenant_id),
            is_requester=False,
            shared_count=0,
        )

    async def end(self, *, actor: User, partnership_id: uuid.UUID) -> None:
        if not await self.gateway.end_partnership(partnership_id):
            raise PartnershipNotFoundError
        await self.audit.record(
            tenant_id=self.tenant_id,
            action=ACTION_END,
            actor_user_id=actor.id,
            partnership_id=partnership_id,
        )

    # ------------------------------------------------- compartilhar (lado dono)

    async def share_lawsuit(
        self, *, actor: User, lawsuit_id: uuid.UUID, payload: ShareLawsuitRequest
    ) -> SharedLawsuit:
        """Regra 3: compartilha UM processo. O processo tem que ser do escritório da
        sessão (o RLS garante) e a parceria tem que estar ativa."""
        if await self.lawsuits.get_by_id(lawsuit_id) is None:
            raise LawsuitNotSharedError
        partnership = await self.partnerships.find_active_with(payload.partnership_id)
        if partnership is None:
            raise PartnershipNotFoundError
        partner_tenant_id = self._other_tenant_id(partnership)
        if partner_tenant_id is None:
            raise PartnershipNotFoundError
        existing = await self.shares.get_active(lawsuit_id, partner_tenant_id)
        if existing is not None:
            existing.can_view_financial = payload.can_view_financial
            existing.can_create_tasks = payload.can_create_tasks
            share = existing
            await self.session.flush()
        else:
            share = await self.shares.create(
                SharedLawsuit(
                    partnership_id=partnership.id,
                    owner_tenant_id=self.tenant_id,
                    partner_tenant_id=partner_tenant_id,
                    lawsuit_id=lawsuit_id,
                    can_view_financial=payload.can_view_financial,
                    can_create_tasks=payload.can_create_tasks,
                    shared_by=actor.id,
                )
            )
        await self.audit.record(
            tenant_id=self.tenant_id,
            action=ACTION_SHARE,
            actor_user_id=actor.id,
            partnership_id=partnership.id,
            lawsuit_id=lawsuit_id,
            detail={
                "can_view_financial": payload.can_view_financial,
                "can_create_tasks": payload.can_create_tasks,
            },
        )
        return share

    async def revoke_share(
        self, *, actor: User, lawsuit_id: uuid.UUID, share_id: uuid.UUID
    ) -> None:
        share = await self.shares.get_by_id(share_id)
        if share is None or share.lawsuit_id != lawsuit_id or share.revoked_at is not None:
            raise LawsuitNotSharedError
        await self.shares.revoke(share)
        await self.audit.record(
            tenant_id=self.tenant_id,
            action=ACTION_REVOKE,
            actor_user_id=actor.id,
            partnership_id=share.partnership_id,
            lawsuit_id=lawsuit_id,
        )

    async def list_shares(self, lawsuit_id: uuid.UUID) -> list[tuple[SharedLawsuit, str | None]]:
        """Regra 12: o processo exibe badge permanente enquanto houver parceiro olhando."""
        shares = list(await self.shares.list_for_lawsuit(lawsuit_id))
        names = await self.partnerships.tenant_names({s.partner_tenant_id for s in shares})
        return [(share, names.get(share.partner_tenant_id)) for share in shares]

    # ---------------------------------------------- compartilhado comigo (lado parceiro)

    async def shared_with_me(self, *, steps: Sequence[int] | None = None) -> list[Row[Any]]:
        rows = list(await self.gateway.shared_lawsuits())
        if steps:
            wanted = set(steps)
            rows = [row for row in rows if row.step_id in wanted]
        return rows

    async def shared_detail(self, lawsuit_id: uuid.UUID) -> SharedLawsuitDetail:
        rows = [row for row in await self.gateway.shared_lawsuits() if row.lawsuit_id == lawsuit_id]
        if not rows:
            raise LawsuitNotSharedError
        return SharedLawsuitDetail(
            lawsuit=rows[0],
            parties=await self.gateway.parties(lawsuit_id),
            timeline=await self.gateway.timeline(lawsuit_id),
            tasks=await self.gateway.tasks(lawsuit_id),
        )

    async def shared_task_types(self, lawsuit_id: uuid.UUID) -> Sequence[Row[Any]]:
        await self._require_scope(lawsuit_id)
        return await self.gateway.task_types(lawsuit_id)

    async def create_partner_task(
        self, *, actor: User, lawsuit_id: uuid.UUID, payload: PartnerTaskCreateRequest
    ) -> uuid.UUID:
        """Regra 5: sem `can_create_tasks` o compartilhamento é só leitura. A checagem
        vem antes da chamada de propósito — deixar o Postgres levantar abortaria a
        transação e derrubaria a auditoria junto."""
        scope = await self._require_scope(lawsuit_id)
        if not scope.can_create_tasks:
            raise SharingForbiddenError
        allowed = {row.id for row in await self.gateway.task_types(lawsuit_id)}
        if payload.task_type_id not in allowed:
            raise InvalidTaskTypeError
        post_id = await self.gateway.create_task(
            lawsuit_id=lawsuit_id,
            task_type_id=payload.task_type_id,
            author_user_id=actor.id,
            scheduled_date=payload.scheduled_date,
            deadline_date=payload.deadline_date,
            comments=payload.comments,
        )
        await self.audit.record(
            tenant_id=self.tenant_id,
            action=ACTION_PARTNER_TASK,
            actor_user_id=actor.id,
            partnership_id=scope.partnership_id,
            lawsuit_id=lawsuit_id,
            detail={"post_id": str(post_id)},
        )
        return post_id

    async def summary(self) -> tuple[int, int, int, int]:
        shared_count, pending_here, pending_partner = await self.gateway.pending_demands()
        partners = await self.partnerships.active_partner_count(self.tenant_id)
        return shared_count, pending_here, pending_partner, partners

    async def _require_scope(self, lawsuit_id: uuid.UUID) -> ShareScope:
        scope = await self.gateway.scope_for(lawsuit_id)
        if scope is None:
            raise LawsuitNotSharedError
        return scope
