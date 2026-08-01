import uuid

import pytest

from app.core.exceptions import InvalidTransferError
from app.core.transfer import validated_transfer


async def test_from_id_igual_a_to_id_levanta_invalid_transfer() -> None:
    entity_id = uuid.uuid4()

    async def get_by_id(_id: uuid.UUID) -> object | None:
        return object()

    async def reassign() -> int:
        raise AssertionError("não deveria reatribuir quando from_id == to_id")

    with pytest.raises(InvalidTransferError):
        await validated_transfer(
            from_id=entity_id, to_id=entity_id, get_by_id=get_by_id, reassign=reassign
        )


async def test_origem_inexistente_levanta_invalid_transfer() -> None:
    to_id = uuid.uuid4()

    async def get_by_id(id_: uuid.UUID) -> object | None:
        return object() if id_ == to_id else None

    async def reassign() -> int:
        raise AssertionError("não deveria reatribuir quando a origem não existe")

    with pytest.raises(InvalidTransferError):
        await validated_transfer(
            from_id=uuid.uuid4(), to_id=to_id, get_by_id=get_by_id, reassign=reassign
        )


async def test_destino_inexistente_levanta_invalid_transfer() -> None:
    from_id = uuid.uuid4()

    async def get_by_id(id_: uuid.UUID) -> object | None:
        return object() if id_ == from_id else None

    async def reassign() -> int:
        raise AssertionError("não deveria reatribuir quando o destino não existe")

    with pytest.raises(InvalidTransferError):
        await validated_transfer(
            from_id=from_id, to_id=uuid.uuid4(), get_by_id=get_by_id, reassign=reassign
        )


async def test_ids_validos_chama_reassign_e_retorna_o_resultado() -> None:
    async def get_by_id(_id: uuid.UUID) -> object | None:
        return object()

    async def reassign() -> int:
        return 3

    result = await validated_transfer(
        from_id=uuid.uuid4(), to_id=uuid.uuid4(), get_by_id=get_by_id, reassign=reassign
    )

    assert result == 3
