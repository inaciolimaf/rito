"""Detecção do tipo de entrada (spec 096, regra 2).

Função pura, sem banco: é a decisão mais importante da busca e a mais fácil de testar
isolada. Digitar um CPF e receber resultado por relevância textual seria absurdo — quem
digita 11 dígitos sabe exatamente quem procura.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

MIN_QUERY_LENGTH = 2

_ONLY_DIGITS = re.compile(r"\D")
# CNJ: NNNNNNN-DD.AAAA.J.TR.OOOO — com ou sem máscara, sempre 20 dígitos.
_CNJ_DIGITS = 20


class QueryKind(StrEnum):
    TOO_SHORT = "too_short"
    DOCUMENT = "document"
    PROCESS_NUMBER = "process_number"
    FULL_TEXT = "full_text"


@dataclass(frozen=True)
class ParsedQuery:
    kind: QueryKind
    raw: str
    digits: str = ""

    @property
    def is_exact(self) -> bool:
        return self.kind in (QueryKind.DOCUMENT, QueryKind.PROCESS_NUMBER)


def parse_query(raw: str) -> ParsedQuery:
    texto = (raw or "").strip()
    if len(texto) < MIN_QUERY_LENGTH:
        # Regra 1 e 12: busca curta não é erro — é o momento de mostrar as recentes.
        return ParsedQuery(kind=QueryKind.TOO_SHORT, raw=texto)

    digitos = _ONLY_DIGITS.sub("", texto)
    somente_digitos_e_mascara = bool(digitos) and not re.search(r"[A-Za-zÀ-ÿ]", texto)
    if somente_digitos_e_mascara:
        if len(digitos) == _CNJ_DIGITS:
            return ParsedQuery(kind=QueryKind.PROCESS_NUMBER, raw=texto, digits=digitos)
        if len(digitos) in (11, 14):
            return ParsedQuery(kind=QueryKind.DOCUMENT, raw=texto, digits=digitos)
    return ParsedQuery(kind=QueryKind.FULL_TEXT, raw=texto)


def to_tsquery_input(raw: str) -> str:
    """Prefixo no último termo: quem digita "Mar" espera achar "Marina" antes de terminar
    de escrever — e é o comportamento que qualquer campo de busca tem hoje."""
    termos = [termo for termo in re.split(r"\s+", raw.strip()) if termo]
    if not termos:
        return ""
    seguros = [_ONLY_SAFE.sub(" ", termo).strip() for termo in termos]
    seguros = [termo for termo in seguros if termo]
    if not seguros:
        return ""
    seguros[-1] = f"{seguros[-1]}:*"
    return " & ".join(seguros)


# Tudo que não é letra, dígito ou espaço vira espaço: os operadores do `tsquery` (`&`,
# `|`, `!`, `:`) viriam do campo de busca do usuário, e um `!` mal colocado transforma a
# consulta em erro de sintaxe do Postgres.
_ONLY_SAFE = re.compile(r"[^0-9A-Za-zÀ-ÿ ]+")
