from datetime import date, time, timedelta

import pytest
from pydantic import ValidationError

from app.domain.users.schemas import UserUpdateRequest

_BASE_PAYLOAD: dict[str, object] = {
    "name": "Fulano de Tal",
    "role": "COLABORADOR",
    "financial_access": "NONE",
}


@pytest.mark.parametrize(
    ("number_oab", "is_valid"),
    [
        ("123456/SP", True),
        ("1234/RJ", True),
        ("12345/DF", True),
        ("123456/sp", False),  # UF minúscula
        ("123456/XX", False),  # UF inexistente
        ("123456SP", False),  # sem barra
        ("123/SP", False),  # menos de 4 dígitos
        ("1234567/SP", False),  # mais de 6 dígitos
        ("123456/S", False),  # UF com 1 letra
    ],
)
def test_validacao_de_oab(number_oab: str, is_valid: bool) -> None:
    payload = {**_BASE_PAYLOAD, "number_oab": number_oab}
    if is_valid:
        assert UserUpdateRequest.model_validate(payload).number_oab == number_oab
    else:
        with pytest.raises(ValidationError):
            UserUpdateRequest.model_validate(payload)


def test_number_oab_none_e_aceito() -> None:
    payload = {**_BASE_PAYLOAD, "number_oab": None}
    assert UserUpdateRequest.model_validate(payload).number_oab is None


@pytest.mark.parametrize(
    ("work_start", "work_end", "work_interval", "is_valid"),
    [
        (time(8, 0), time(18, 0), timedelta(hours=1), True),
        (time(8, 0), time(18, 0), None, True),
        (None, None, None, True),
        (time(18, 0), time(8, 0), None, False),  # fim antes do início
        (time(8, 0), time(8, 0), None, False),  # fim igual ao início
        (time(8, 0), time(18, 0), timedelta(hours=10), False),  # intervalo == jornada
        (time(8, 0), time(18, 0), timedelta(hours=11), False),  # intervalo > jornada
    ],
)
def test_validacao_de_jornada(
    work_start: time | None,
    work_end: time | None,
    work_interval: timedelta | None,
    is_valid: bool,
) -> None:
    payload = {
        **_BASE_PAYLOAD,
        "work_start": work_start,
        "work_end": work_end,
        "work_interval": work_interval,
    }
    if is_valid:
        UserUpdateRequest.model_validate(payload)
    else:
        with pytest.raises(ValidationError):
            UserUpdateRequest.model_validate(payload)


@pytest.mark.parametrize(
    ("admission_date", "resignation_date", "is_valid"),
    [
        (date(2020, 1, 1), date(2021, 1, 1), True),
        (date(2020, 1, 1), date(2020, 1, 1), True),
        (date(2021, 1, 1), date(2020, 1, 1), False),
        (None, None, True),
    ],
)
def test_validacao_de_admissao_e_demissao(
    admission_date: date | None, resignation_date: date | None, is_valid: bool
) -> None:
    payload = {
        **_BASE_PAYLOAD,
        "admission_date": admission_date,
        "resignation_date": resignation_date,
    }
    if is_valid:
        UserUpdateRequest.model_validate(payload)
    else:
        with pytest.raises(ValidationError):
            UserUpdateRequest.model_validate(payload)
