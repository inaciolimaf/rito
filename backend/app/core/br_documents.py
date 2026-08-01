"""Validação de CPF/CNPJ com o algoritmo real (dígito verificador mod 11) — spec 011
regra 1. Compartilhado: o ADVBOX exige esse mesmo algoritmo em accounts (011), pessoas
(016+) e transações (financeiro), então mora em `core`, não em `domain/account`."""

import re

_NON_DIGITS = re.compile(r"\D")


def strip_document_mask(value: str) -> str:
    """Remove pontos, traço e barra — o banco guarda só dígitos (spec 011, regra 1)."""
    return _NON_DIGITS.sub("", value)


def _check_digit(digits: str, weights: list[int]) -> int:
    total = sum(int(digit) * weight for digit, weight in zip(digits, weights, strict=True))
    remainder = total % 11
    return 0 if remainder < 2 else 11 - remainder


def is_valid_cpf(value: str) -> bool:
    digits = strip_document_mask(value)
    if len(digits) != 11 or digits == digits[0] * 11:
        return False

    first_digit = _check_digit(digits[:9], list(range(10, 1, -1)))
    second_digit = _check_digit(digits[:9] + str(first_digit), list(range(11, 1, -1)))
    return digits[9:] == f"{first_digit}{second_digit}"


def is_valid_cnpj(value: str) -> bool:
    digits = strip_document_mask(value)
    if len(digits) != 14 or digits == digits[0] * 14:
        return False

    first_weights = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    second_weights = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    first_digit = _check_digit(digits[:12], first_weights)
    second_digit = _check_digit(digits[:12] + str(first_digit), second_weights)
    return digits[12:] == f"{first_digit}{second_digit}"


def is_valid_cpf_or_cnpj(value: str) -> bool:
    digits = strip_document_mask(value)
    if len(digits) == 11:
        return is_valid_cpf(digits)
    if len(digits) == 14:
        return is_valid_cnpj(digits)
    return False


# Os 26 estados + Distrito Federal (docs/ADVBOX-ESPECIFICACAO-COMPLETA.md linha 817:
# "Todos os 27 estados + DF" — usado por account (011) e OAB/UF de usuários (012).
BRAZILIAN_UFS = frozenset(
    {
        "AC",
        "AL",
        "AP",
        "AM",
        "BA",
        "CE",
        "DF",
        "ES",
        "GO",
        "MA",
        "MT",
        "MS",
        "MG",
        "PA",
        "PB",
        "PR",
        "PE",
        "PI",
        "RJ",
        "RN",
        "RS",
        "RO",
        "RR",
        "SC",
        "SP",
        "SE",
        "TO",
    }
)
