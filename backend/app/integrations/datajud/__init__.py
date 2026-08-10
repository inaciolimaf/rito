"""Integração com o DataJud (spec 046) — client HTTP + parser puro."""

from app.integrations.datajud.client import (
    DatajudApiError,
    DatajudClient,
    DatajudConfigError,
    DatajudUnauthorizedError,
)
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
    "ParsedMovement",
    "ParsedMovementComplement",
    "ParsedProcess",
    "ParsedSubject",
    "normalize_process_number",
    "parse_process",
]
