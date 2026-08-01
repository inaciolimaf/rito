import pytest
from fastapi import HTTPException

from app.core.http import get_or_404, parse_active_status


async def test_get_or_404_retorna_o_valor_quando_encontrado() -> None:
    result = await get_or_404(lambda: _found("valor"), "não encontrado")
    assert result == "valor"


async def test_get_or_404_levanta_404_quando_none() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_or_404(lambda: _found(None), "não encontrado")
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "não encontrado"


async def _found[T](value: T) -> T:
    return value


def test_parse_active_status_active_vira_true() -> None:
    assert parse_active_status("active") is True


def test_parse_active_status_inactive_vira_false() -> None:
    assert parse_active_status("inactive") is False


def test_parse_active_status_none_permanece_none() -> None:
    assert parse_active_status(None) is None
