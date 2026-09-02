"""Integração com o DataJud (spec 046) — contrato `LawsuitSource`, client HTTP e parser puro."""

from app.integrations.datajud.base import (
    DatajudApiError,
    DatajudConfigError,
    DatajudUnauthorizedError,
    LawsuitSource,
)
from app.integrations.datajud.client import DatajudClient
from app.integrations.datajud.parser import (
    DatajudParseError,
    ParsedMovement,
    ParsedMovementComplement,
    ParsedProcess,
    ParsedSubject,
    normalize_process_number,
    parse_process,
)

__all__ = [
    "DatajudApiError",
    "DatajudClient",
    "DatajudConfigError",
    "DatajudParseError",
    "DatajudUnauthorizedError",
    "LawsuitSource",
    "ParsedMovement",
    "ParsedMovementComplement",
    "ParsedProcess",
    "ParsedSubject",
    "normalize_process_number",
    "parse_process",
]
