import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.domain.lawsuits.cnj import (
    CNJValidationError,
    compute_check_digit,
    format_cnj,
    infer_court_code,
    parse_cnj,
)

_FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "cnj_numbers.json"


def _load_fixtures() -> list[dict[str, object]]:
    with _FIXTURE_PATH.open(encoding="utf-8") as fixture_file:
        result: list[dict[str, object]] = json.load(fixture_file)
        return result


@pytest.mark.parametrize("case", _load_fixtures(), ids=lambda case: case["masked"])
def test_vinte_numeros_reais_validos(case: dict[str, object]) -> None:
    """Tabela de 20 números válidos cobrindo os 9 segmentos (spec 025 §8)."""
    parsed = parse_cnj(str(case["masked"]))

    assert parsed.year == case["year"]
    assert parsed.segment == case["segment"]
    assert format_cnj(parsed) == case["masked"]
    # Regra 1: só dígitos também é aceito e dá no mesmo parse.
    assert parse_cnj(str(case["digits"])) == parsed


def test_dv_invalido_rejeitado() -> None:
    with pytest.raises(CNJValidationError, match="Dígito verificador não confere"):
        parse_cnj("0000123-77.2025.1.00.0001")


@pytest.mark.parametrize("value", ["123", "000012376202510000011", "0000123-76.2025.1.00.001"])
def test_comprimento_errado_rejeitado(value: str) -> None:
    with pytest.raises(CNJValidationError, match="20 dígitos"):
        parse_cnj(value)


@pytest.mark.parametrize("year", ["1899", str(datetime.now(UTC).year + 2)])
def test_ano_fora_do_intervalo_rejeitado(year: str) -> None:
    with pytest.raises(CNJValidationError, match="Ano do processo fora do intervalo"):
        parse_cnj(f"0000123-76.{year}.1.00.0001")


def test_segmento_invalido_rejeitado() -> None:
    with pytest.raises(CNJValidationError, match="Segmento de justiça inválido"):
        parse_cnj("0000123-00.2025.0.00.0001")


@pytest.mark.parametrize(
    "value",
    [
        "0000123-76.2025.1.00.0001",  # com máscara
        "00001237620251000001",  # só dígitos
        " 0000123-76.2025.1.00.0001 ",  # com espaços
        "0000123 76 2025 1 00 0001",  # só espaços
    ],
)
def test_normaliza_com_mascara_sem_mascara_e_espacos(value: str) -> None:
    parsed = parse_cnj(value)
    assert parsed.sequential == "0000123"
    assert parsed.check_digit == "76"


@pytest.mark.parametrize(
    ("masked", "expected_code"),
    [
        ("0700700-18.2025.8.26.0100", "TJSP"),
        ("0100100-97.2025.5.02.0101", "TRT2"),
        ("0044556-97.2025.4.04.7200", "TRF4"),
    ],
)
def test_infere_tribunal(masked: str, expected_code: str) -> None:
    assert infer_court_code(parse_cnj(masked)) == expected_code


def test_tribunal_desconhecido_retorna_none_sem_invalidar() -> None:
    # Segmento 8 com TR 28 (não existe UF 28) — número válido, sem tribunal no mapa.
    digits18 = "0000123" + "2025" + "8" + "28" + "0100"
    masked = f"0000123-{compute_check_digit(digits18)}.2025.8.28.0100"
    parsed = parse_cnj(masked)
    assert parsed.court == "28"
    assert infer_court_code(parsed) is None
