"""A fronteira do tenant (spec 079 §9).

Este é o ÚNICO módulo do sistema que lê e escreve dado de outro escritório, e ele não
sabe fazer isso sozinho: cada chamada é uma função `SECURITY DEFINER` da migration 079,
e toda uma delas repete o mesmo guarda dentro do banco — existe compartilhamento ATIVO
daquele processo para `current_setting('app.tenant_id')`. Nenhuma política de RLS foi
afrouxada para isto funcionar: se este módulo sumir, o parceiro volta a não enxergar
absolutamente nada do dono (é o teste de vazamento que garante).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncSession

TIMELINE_LIMIT = 50


@dataclass(frozen=True)
class ShareScope:
    """O escopo com que o escritório da sessão enxerga um processo do parceiro."""

    share_id: uuid.UUID
    partnership_id: uuid.UUID
    owner_tenant_id: uuid.UUID
    can_view_financial: bool
    can_create_tasks: bool


class PartnerGateway:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def scope_for(self, lawsuit_id: uuid.UUID) -> ShareScope | None:
        row = (
            await self.session.execute(
                text("SELECT * FROM partner_share_for(:lawsuit_id)"),
                {"lawsuit_id": lawsuit_id},
            )
        ).first()
        if row is None:
            return None
        return ShareScope(
            share_id=row.share_id,
            partnership_id=row.partnership_id,
            owner_tenant_id=row.owner_tenant_id,
            can_view_financial=row.can_view_financial,
            can_create_tasks=row.can_create_tasks,
        )

    async def shared_lawsuits(self) -> Sequence[Row[Any]]:
        return (await self.session.execute(text("SELECT * FROM partner_shared_lawsuits()"))).all()

    async def parties(self, lawsuit_id: uuid.UUID) -> Sequence[Row[Any]]:
        return (
            await self.session.execute(
                text("SELECT * FROM partner_shared_parties(:lawsuit_id)"),
                {"lawsuit_id": lawsuit_id},
            )
        ).all()

    async def timeline(
        self, lawsuit_id: uuid.UUID, *, limit: int = TIMELINE_LIMIT
    ) -> Sequence[Row[Any]]:
        return (
            await self.session.execute(
                text("SELECT * FROM partner_shared_timeline(:lawsuit_id, :limit)"),
                {"lawsuit_id": lawsuit_id, "limit": limit},
            )
        ).all()

    async def tasks(self, lawsuit_id: uuid.UUID) -> Sequence[Row[Any]]:
        return (
            await self.session.execute(
                text("SELECT * FROM partner_shared_tasks(:lawsuit_id)"),
                {"lawsuit_id": lawsuit_id},
            )
        ).all()

    async def task_types(self, lawsuit_id: uuid.UUID) -> Sequence[Row[Any]]:
        return (
            await self.session.execute(
                text("SELECT * FROM partner_shared_task_types(:lawsuit_id)"),
                {"lawsuit_id": lawsuit_id},
            )
        ).all()

    async def create_task(
        self,
        *,
        lawsuit_id: uuid.UUID,
        task_type_id: uuid.UUID,
        author_user_id: uuid.UUID,
        scheduled_date: date | None,
        deadline_date: date | None,
        comments: str | None,
    ) -> uuid.UUID:
        """Única escrita cross-tenant do sistema (regra 5). A função repete o guarda de
        `can_create_tasks` — o service já checou antes justamente para responder 403 sem
        abortar a transação com a exceção do Postgres."""
        post_id = await self.session.scalar(
            text(
                "SELECT partner_create_task(:lawsuit_id, :task_type_id, :author_user_id, "
                ":scheduled_date, :deadline_date, :comments)"
            ),
            {
                "lawsuit_id": lawsuit_id,
                "task_type_id": task_type_id,
                "author_user_id": author_user_id,
                "scheduled_date": scheduled_date,
                "deadline_date": deadline_date,
                "comments": comments,
            },
        )
        return uuid.UUID(str(post_id))

    async def accept_invite(self, token_hash: str, email: str) -> uuid.UUID | None:
        """O convite mora no tenant de quem convidou — sem esta função o convidado não
        enxergaria a linha para aceitá-la."""
        accepted = await self.session.scalar(
            text("SELECT partnership_accept(:token_hash, :email)"),
            {"token_hash": token_hash, "email": email},
        )
        return uuid.UUID(str(accepted)) if accepted is not None else None

    async def end_partnership(self, partnership_id: uuid.UUID) -> bool:
        """Regra 7: encerra e revoga os compartilhamentos dos DOIS lados."""
        ended = await self.session.scalar(
            text("SELECT partnership_end(:partnership_id)"),
            {"partnership_id": partnership_id},
        )
        return bool(ended)

    async def email_has_account(self, email: str) -> bool:
        """Regra 2: sem conta no Rito, o convite é de cadastro e a parceria fica PENDENTE."""
        return bool(
            await self.session.scalar(
                text("SELECT partnership_email_has_account(:email)"), {"email": email}
            )
        )

    async def pending_demands(self) -> tuple[int, int, int]:
        """(processos compartilhados, demanda do meu escritório, demanda do parceiro) —
        regra 10, calculado das duas pontas pelo tenant do responsável pela tarefa."""
        row = (await self.session.execute(text("SELECT * FROM partner_pending_demands()"))).one()
        return int(row.shared_count), int(row.pending_here), int(row.pending_partner)
