"""Número único do processo (NUP/CNJ — Resolução CNJ 65/2008).

Módulo puro (spec 025 §10): sem FastAPI, sem SQLAlchemy, sem I/O — só parsing,
validação do dígito verificador (módulo 97 base 10, ISO 7064) e inferência de tribunal.
"""

from collections.abc import Callable
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


def _validate_cnj(digits: str, *, year: int, segment: int, check_digit: str) -> None:
    """Regra 3: cada recusa diz a causa exata, nunca «número inválido».

    A ordem é do mais barato ao mais caro e do mais provável ao menos: ano e segmento são
    comparações diretas e pegam o erro de digitação comum; o dígito verificador exige o
    cálculo do módulo 97 e fica por último. Quem digitou errado o ano lê «ano fora do
    intervalo», não «dígito não confere», que não ajudaria ninguém a corrigir.
    """
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
    _validate_cnj(digits, year=year, segment=segment, check_digit=check_digit)

    return CNJNumber(
        sequential=sequential,
        check_digit=check_digit,
        year=year,
        segment=segment,
        court=court,
        origin=origin,
    )


def _regional(prefixo: str, court: str, teto: int) -> str | None:
    """`TRF1`..`TRF6`, `TRT1`..`TRT24` — região fora da faixa não existe no catálogo."""
    regiao = int(court)
    return f"{prefixo}{regiao}" if 1 <= regiao <= teto else None


def _eleitoral(court: str) -> str | None:
    uf = _UFS_BY_CNJ_TR.get(int(court))
    return f"TRE-{uf}" if uf else None


def _estadual(court: str) -> str | None:
    uf = _UFS_BY_CNJ_TR.get(int(court))
    if uf is None:
        return None
    # O DF tem tribunal único para Distrito Federal e Territórios.
    return "TJDFT" if uf == "DF" else f"TJ{uf}"


def _militar_estadual(court: str) -> str | None:
    """Só três estados têm justiça militar própria (MG, RS e SP)."""
    uf = _UFS_BY_CNJ_TR.get(int(court))
    return f"TJM-{uf}" if uf in ("MG", "RS", "SP") else None


# Regra 7: segmento do CNJ → como o código do tribunal sai do TR. Tabela em vez de cadeia
# de `if segment == N` (spec 106) — cada segmento é uma linha, e a superior (o tribunal de
# cúpula do segmento, quando TR é "00") fica ao lado da regional, que é como a regra é
# realmente escrita na resolução do CNJ.
_SEGMENTOS: dict[int, tuple[str | None, Callable[[str], str | None] | None]] = {
    1: ("STF", None),
    2: ("CNJ", None),
    3: ("STJ", None),
    4: (None, lambda court: _regional("TRF", court, 6)),
    5: ("TST", lambda court: _regional("TRT", court, 24)),
    6: ("TSE", _eleitoral),
    7: ("STM", None),
    8: (None, _estadual),
    9: (None, _militar_estadual),
}


def infer_court_code(number: CNJNumber) -> str | None:
    """Código do tribunal no catálogo (spec 021) a partir de J+TR (regra 7).

    Retorna None quando a combinação não tem correspondência — sem invalidar o número.
    """
    entrada = _SEGMENTOS.get(number.segment)
    if entrada is None:
        return None
    cupula, regional = entrada
    if regional is None:
        return cupula
    if cupula is not None and number.court == "00":
        return cupula
    codigo: str | None = regional(number.court)
    return codigo
