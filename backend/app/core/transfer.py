import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.exceptions import InvalidTransferError


async def validated_transfer[T](
    *,
    from_id: uuid.UUID,
    to_id: uuid.UUID,
    get_by_id: Callable[[uuid.UUID], Awaitable[T | None]],
    reassign: Callable[[], Awaitable[int]],
) -> int:
    """Guarda comum a todo fluxo "transferir antes de excluir" (regra duplicada em
    customer_origins/016, action_groups+lawsuit_types/014, stages/015, spec 020): ids
    iguais ou inexistentes nunca chegam a `reassign`. A reatribuição em si é específica de
    cada domínio (real em alguns, no-op documentado em outros) — só a validação é comum.
    """
    if from_id == to_id:
        raise InvalidTransferError
    from_entity = await get_by_id(from_id)
    to_entity = await get_by_id(to_id)
    if from_entity is None or to_entity is None:
        raise InvalidTransferError
    return await reassign()


async def count_references(
    session: AsyncSession, *, column: InstrumentedAttribute[Any], target_id: uuid.UUID
) -> int:
    """Quantas linhas apontam para `target_id` pela coluna dada — o "está em uso?" das
    guardas de exclusão.

    Extraído na spec 101 pela regra dos 3 usos (CLAUDE.md §6): a mesma contagem aparece
    em etapas→lawsuits, origens→customers, categorias→transactions e centros→transactions.
    Contas bancárias NÃO usam esta função de propósito — lá a referência é por duas
    colunas (`debit_account_id`/`credit_account_id`), e espremer o OR aqui deixaria a
    assinatura pior para os quatro casos simples.
    """
    stmt = select(func.count()).where(column == target_id)
    return int((await session.execute(stmt)).scalar_one())


async def reassign_references(
    session: AsyncSession,
    *,
    column: InstrumentedAttribute[Any],
    from_id: uuid.UUID,
    to_id: uuid.UUID,
) -> int:
    """UPDATE em lote da coluna, devolvendo quantas linhas mudaram — o `transferred_count`
    real dos endpoints de transferência. Par de `count_references` (spec 101)."""
    result = await session.execute(
        update(column.parent.class_)
        .where(column == from_id)
        .values({column.key: to_id})
        .execution_options(synchronize_session=False)
    )
    return int(result.rowcount)  # type: ignore[attr-defined]  # SQLAlchemy tipa `rowcount` só em `CursorResult`; um UPDATE sempre devolve um.
