"""Acesso a dados do próprio tenant (as duas tabelas da parceria + auditoria).

Tudo que atravessa a fronteira do tenant mora em `sharing.py` — aqui só há query
comum, sujeita ao RLS como qualquer outro repositório do projeto.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, or_, select, update

from app.core.models import Tenant
from app.core.repository import BaseRepository
from app.domain.partnerships.models import (
    Partnership,
    PartnershipAuditLog,
    PartnershipStatus,
    SharedLawsuit,
)


class PartnershipRepository(BaseRepository[Partnership]):
    model = Partnership

    async def list_for_tenant(
        self, *, status: PartnershipStatus | None = None
    ) -> Sequence[Partnership]:
        """O RLS já limita às parcerias em que o tenant da sessão é uma das pontas."""
        stmt = select(Partnership).order_by(Partnership.created_at.desc())
        if status is not None:
            stmt = stmt.where(Partnership.status == status)
        return (await self.session.scalars(stmt)).all()

    async def get_by_invited_email(self, email: str) -> Partnership | None:
        stmt = select(Partnership).where(Partnership.invited_email == email)
        return (await self.session.scalars(stmt)).first()

    async def find_active_with(self, partnership_id: uuid.UUID) -> Partnership | None:
        stmt = select(Partnership).where(
            Partnership.id == partnership_id,
            Partnership.status == PartnershipStatus.ATIVA,
        )
        return (await self.session.scalars(stmt)).first()

    async def create(self, partnership: Partnership) -> Partnership:
        self.session.add(partnership)
        await self.session.flush()
        return partnership

    async def tenant_names(self, tenant_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        """`tenants` não tem RLS (é a tabela raiz) — o nome do escritório parceiro é o
        único dado dele que aparece sem passar por compartilhamento."""
        if not tenant_ids:
            return {}
        stmt = select(Tenant.id, Tenant.name).where(Tenant.id.in_(tenant_ids))
        return {row.id: row.name for row in await self.session.execute(stmt)}

    async def active_partner_count(self, tenant_id: uuid.UUID) -> int:
        stmt = select(func.count()).where(
            Partnership.status == PartnershipStatus.ATIVA,
            or_(
                Partnership.requester_tenant_id == tenant_id,
                Partnership.partner_tenant_id == tenant_id,
            ),
        )
        return int(await self.session.scalar(stmt) or 0)


class SharedLawsuitRepository(BaseRepository[SharedLawsuit]):
    model = SharedLawsuit

    async def list_for_lawsuit(
        self, lawsuit_id: uuid.UUID, *, include_revoked: bool = False
    ) -> Sequence[SharedLawsuit]:
        stmt = (
            select(SharedLawsuit)
            .where(SharedLawsuit.lawsuit_id == lawsuit_id)
            .order_by(SharedLawsuit.created_at.desc())
        )
        if not include_revoked:
            stmt = stmt.where(SharedLawsuit.revoked_at.is_(None))
        return (await self.session.scalars(stmt)).all()

    async def get_active(
        self, lawsuit_id: uuid.UUID, partner_tenant_id: uuid.UUID
    ) -> SharedLawsuit | None:
        stmt = select(SharedLawsuit).where(
            SharedLawsuit.lawsuit_id == lawsuit_id,
            SharedLawsuit.partner_tenant_id == partner_tenant_id,
            SharedLawsuit.revoked_at.is_(None),
        )
        return (await self.session.scalars(stmt)).first()

    async def count_active_for_partnership(self, partnership_id: uuid.UUID) -> int:
        stmt = select(func.count()).where(
            SharedLawsuit.partnership_id == partnership_id,
            SharedLawsuit.revoked_at.is_(None),
        )
        return int(await self.session.scalar(stmt) or 0)

    async def counts_by_partnership(self) -> dict[uuid.UUID, int]:
        stmt = (
            select(SharedLawsuit.partnership_id, func.count())
            .where(SharedLawsuit.revoked_at.is_(None))
            .group_by(SharedLawsuit.partnership_id)
        )
        return {row[0]: int(row[1]) for row in await self.session.execute(stmt)}

    async def create(self, share: SharedLawsuit) -> SharedLawsuit:
        self.session.add(share)
        await self.session.flush()
        return share

    async def revoke(self, share: SharedLawsuit) -> None:
        """Regra 6: corta o acesso na hora — a linha continua como histórico."""
        await self.session.execute(
            update(SharedLawsuit)
            .where(SharedLawsuit.id == share.id, SharedLawsuit.revoked_at.is_(None))
            .values(revoked_at=func.now())
        )


class PartnershipAuditRepository(BaseRepository[PartnershipAuditLog]):
    model = PartnershipAuditLog

    async def record(
        self,
        *,
        tenant_id: uuid.UUID,
        action: str,
        actor_user_id: uuid.UUID | None,
        partnership_id: uuid.UUID | None = None,
        lawsuit_id: uuid.UUID | None = None,
        detail: dict[str, object] | None = None,
    ) -> PartnershipAuditLog:
        """Regra 11: toda ação de compartilhamento é auditada."""
        entry = PartnershipAuditLog(
            tenant_id=tenant_id,
            partnership_id=partnership_id,
            lawsuit_id=lawsuit_id,
            action=action,
            actor_user_id=actor_user_id,
            detail=detail or {},
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def list_for_partnership(
        self, partnership_id: uuid.UUID
    ) -> Sequence[PartnershipAuditLog]:
        stmt = (
            select(PartnershipAuditLog)
            .where(PartnershipAuditLog.partnership_id == partnership_id)
            .order_by(PartnershipAuditLog.created_at.desc())
        )
        return (await self.session.scalars(stmt)).all()
