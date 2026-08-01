import uuid
from collections.abc import Awaitable, Callable

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
