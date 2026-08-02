"""Número único do processo (NUP/CNJ — Resolução CNJ 65/2008).

Módulo puro (spec 025 §10): sem FastAPI, sem SQLAlchemy, sem I/O — só parsing,
validação do dígito verificador (módulo 97 base 10, ISO 7064) e inferência de tribunal.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

# Segmento (J) do número CNJ — spec 025 §4.
SEGMENT_NAMES: dict[int, str] = {
    1: "Supremo Tribunal Federal",
    2: "Conselho Nacional de Justiça",
    3: "Superior Tribunal de Justiça",
    4: "Justiça Federal",
    5: "Justiça do Trabalho",
    6: "Justiça Eleitoral",
    7: "Justiça Militar da União",
    8: "Justiça Estadual",
    9: "Justiça Militar Estadual",
}

# Código de tribunal (TR) do CNJ para TJs/TREs/TJMs: 01–27 em ordem alfabética de UF.
_UFS_BY_CNJ_TR: dict[int, str] = {
    1: "AC",
    2: "AL",
    3: "AP",
    4: "AM",
    5: "BA",
    6: "CE",
    7: "DF",
    8: "ES",
    9: "GO",
    10: "MA",
    11: "MT",
    12: "MS",
    13: "MG",
    14: "PA",
    15: "PB",
    16: "PR",
    17: "PE",
    18: "PI",
    19: "RJ",
    20: "RN",
    21: "RS",
    22: "RO",
    23: "RR",
    24: "SC",
    25: "SE",
    26: "SP",
    27: "TO",
}


class CNJValidationError(ValueError):
    """Número CNJ inválido — a mensagem é sempre específica (regras 2–6)."""


@dataclass(frozen=True)
class CNJNumber:
    sequential: str  # 7 dígitos
    check_digit: str  # 2
    year: int  # 4
    segment: int  # 1 (J)
    court: str  # 2 (TR)
    origin: str  # 4 (OOOO)


def compute_check_digit(digits18: str) -> str:
    """DV por módulo 97 base 10 (regra 2): 98 − (concatenação dos 18 dígitos mod 97)."""
    return str(98 - (int(digits18) % 97)).zfill(2)


def format_cnj(number: CNJNumber) -> str:
    """Máscara de apresentação (regra 9: o armazenamento é só dígitos)."""
    return (
        f"{number.sequential}-{number.check_digit}.{number.year}."
        f"{number.segment}.{number.court}.{number.origin}"
    )


def parse_cnj(value: str) -> CNJNumber:
    """Normaliza (regra 1: aceita com/sem máscara e espaços) e valida.

    Levanta CNJValidationError com a causa exata — nunca falha silencioso (regra 3).
    """
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) != 20:
        raise CNJValidationError(
            f"Número do processo deve ter 20 dígitos, recebidos {len(digits)}."
        )

    sequential, check_digit = digits[:7], digits[7:9]
    year = int(digits[9:13])
    segment = int(digits[13])
    court, origin = digits[14:16], digits[16:20]

    max_year = datetime.now(UTC).year + 1
    if not 1900 <= year <= max_year:
        raise CNJValidationError(f"Ano do processo fora do intervalo 1900–{max_year}: {year}.")
    if segment not in SEGMENT_NAMES:
        raise CNJValidationError(f"Segmento de justiça inválido: {segment}.")

    expected = compute_check_digit(digits[:7] + digits[9:20])
    if check_digit != expected:
        raise CNJValidationError(
            f"Dígito verificador não confere: informado {check_digit}, esperado {expected}."
        )

    return CNJNumber(
        sequential=sequential,
        check_digit=check_digit,
        year=year,
        segment=segment,
        court=court,
        origin=origin,
    )


def infer_court_code(number: CNJNumber) -> str | None:
    """Código do tribunal no catálogo (spec 021) a partir de J+TR (regra 7).

    Retorna None quando a combinação não tem correspondência — sem invalidar o número.
    """
    segment, court = number.segment, number.court
    if segment == 1:
        return "STF"
    if segment == 2:
        return "CNJ"
    if segment == 3:
        return "STJ"
    if segment == 4:
        region = int(court)
        return f"TRF{region}" if 1 <= region <= 6 else None
    if segment == 5:
        if court == "00":
            return "TST"
        region = int(court)
        return f"TRT{region}" if 1 <= region <= 24 else None
    if segment == 6:
        if court == "00":
            return "TSE"
        uf = _UFS_BY_CNJ_TR.get(int(court))
        return f"TRE-{uf}" if uf else None
    if segment == 7:
        return "STM"
    if segment == 8:
        uf = _UFS_BY_CNJ_TR.get(int(court))
        if uf is None:
            return None
        return "TJDFT" if uf == "DF" else f"TJ{uf}"
    if segment == 9:
        uf = _UFS_BY_CNJ_TR.get(int(court))
        if uf not in ("MG", "RS", "SP"):
            return None
        return f"TJM-{uf}"
    return None
