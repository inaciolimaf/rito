"""A fronteira do tenant (spec 079 §9).

Este é o ÚNICO módulo do sistema que lê e escreve dado de outro escritório, e ele não
sabe fazer isso sozinho: cada chamada é uma função `SECURITY DEFINER` da migration 079,
e toda uma delas repete o mesmo guarda dentro do banco — existe compartilhamento ATIVO
daquele processo para `current_setting('app.tenant_id')`. Nenhuma política de RLS foi
afrouxada para isto funcionar: se este módulo sumir, o parceiro volta a não enxergar
absolutamente nada do dono (é o teste de vazamento que garante).

## Como as funções são chamadas (spec 127)

`SELECT * FROM f(:x)` virou `select(func.f(x).table_valued(*colunas))`, e as tuplas de
`_COLUNAS_*` abaixo são a lista de colunas de cada `RETURNS TABLE` da migration.

Escrever os nomes aqui parece duplicação e **não é**: sem eles o `.first()` devolvia uma
`Row` cujos atributos só existiam em tempo de execução, e um `row.can_create_tasks` que
não existisse mais só aparecia quando o endpoint quebrasse. Agora as colunas são um dado
do módulo — e `test_partner_gateway_declara_as_colunas_das_funcoes` confere cada tupla
contra o `pg_proc` do banco, de modo que a migration e o Python não podem divergir em
silêncio.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import Row, func, literal, select
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession

TIMELINE_LIMIT = 50

# As colunas de cada `RETURNS TABLE` da migration 079 — na ordem em que ela as declara.
COLUNAS_SHARE_FOR = (
    "share_id",
    "partnership_id",
    "owner_tenant_id",
    "can_view_financial",
    "can_create_tasks",
)
COLUNAS_SHARED_LAWSUITS = (
    "share_id",
    "partnership_id",
    "lawsuit_id",
    "owner_tenant_id",
    "owner_name",
    "process_number",
    "folder",
    "stage_name",
    "step_id",
    "can_view_financial",
    "can_create_tasks",
    "case_value",
    "fees_value",
    "open_tasks",
    "shared_at",
)
COLUNAS_SHARED_PARTIES = ("pole", "name", "is_client")
COLUNAS_SHARED_TIMELINE = ("id", "occurred_at", "title", "body", "origin")
COLUNAS_SHARED_TASKS = (
    "id",
    "task_type_name",
    "scheduled_date",
    "deadline_date",
    "comments",
    "completed",
    "from_partner",
    "created_at",
)
COLUNAS_SHARED_TASK_TYPES = ("id", "name")
COLUNAS_PENDING_DEMANDS = ("shared_count", "pending_here", "pending_partner")


# O tipo vai JUNTO de cada parâmetro porque, numa chamada de função, não há coluna de
# destino para o asyncpg inferi-lo — e o Postgres resolve a sobrecarga pelo tipo do
# argumento. `partnership_accept`/`partnership_email_has_account` recebem `citext`, e um
# `varchar` não casa com elas: sem o `_citext` abaixo o banco responde
# «function partnership_email_has_account(character varying) does not exist».
def _uuid(valor: uuid.UUID) -> Any:
    return literal(valor, PGUUID(as_uuid=True))


def _citext(valor: str) -> Any:
    return literal(valor, CITEXT())


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
        funcao = func.partner_share_for(_uuid(lawsuit_id)).table_valued(*COLUNAS_SHARE_FOR)
        row = (await self.session.execute(select(funcao))).first()
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
        funcao = func.partner_shared_lawsuits().table_valued(*COLUNAS_SHARED_LAWSUITS)
        return (await self.session.execute(select(funcao))).all()

    async def parties(self, lawsuit_id: uuid.UUID) -> Sequence[Row[Any]]:
        funcao = func.partner_shared_parties(_uuid(lawsuit_id)).table_valued(
            *COLUNAS_SHARED_PARTIES
        )
        return (await self.session.execute(select(funcao))).all()

    async def timeline(
        self, lawsuit_id: uuid.UUID, *, limit: int = TIMELINE_LIMIT
    ) -> Sequence[Row[Any]]:
        funcao = func.partner_shared_timeline(_uuid(lawsuit_id), limit).table_valued(
            *COLUNAS_SHARED_TIMELINE
        )
        return (await self.session.execute(select(funcao))).all()

    async def tasks(self, lawsuit_id: uuid.UUID) -> Sequence[Row[Any]]:
        funcao = func.partner_shared_tasks(_uuid(lawsuit_id)).table_valued(*COLUNAS_SHARED_TASKS)
        return (await self.session.execute(select(funcao))).all()

    async def task_types(self, lawsuit_id: uuid.UUID) -> Sequence[Row[Any]]:
        funcao = func.partner_shared_task_types(_uuid(lawsuit_id)).table_valued(
            *COLUNAS_SHARED_TASK_TYPES
        )
        return (await self.session.execute(select(funcao))).all()

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
            select(
                func.partner_create_task(
                    _uuid(lawsuit_id),
                    _uuid(task_type_id),
                    _uuid(author_user_id),
                    scheduled_date,
                    deadline_date,
                    comments,
                )
            )
        )
        return uuid.UUID(str(post_id))

    async def accept_invite(self, token_hash: str, email: str) -> uuid.UUID | None:
        """O convite mora no tenant de quem convidou — sem esta função o convidado não
        enxergaria a linha para aceitá-la."""
        accepted = await self.session.scalar(
            select(func.partnership_accept(token_hash, _citext(email)))
        )
        return uuid.UUID(str(accepted)) if accepted is not None else None

    async def end_partnership(self, partnership_id: uuid.UUID) -> bool:
        """Regra 7: encerra e revoga os compartilhamentos dos DOIS lados."""
        ended = await self.session.scalar(select(func.partnership_end(_uuid(partnership_id))))
        return bool(ended)

    async def email_has_account(self, email: str) -> bool:
        """Regra 2: sem conta no Rito, o convite é de cadastro e a parceria fica PENDENTE."""
        return bool(
            await self.session.scalar(select(func.partnership_email_has_account(_citext(email))))
        )

    async def pending_demands(self) -> tuple[int, int, int]:
        """(processos compartilhados, demanda do meu escritório, demanda do parceiro) —
        regra 10, calculado das duas pontas pelo tenant do responsável pela tarefa."""
        funcao = func.partner_pending_demands().table_valued(*COLUNAS_PENDING_DEMANDS)
        row = (await self.session.execute(select(funcao))).one()
        return int(row.shared_count), int(row.pending_here), int(row.pending_partner)
