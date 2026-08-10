"""Integração com o DJEN (spec 042) — client HTTP + parser puro."""

from app.integrations.djen.client import (
    MAX_PER_PAGE,
    DjenApiError,
    DjenClient,
    DjenConfigError,
    DjenPage,
)
from app.integrations.djen.parser import (
    DjenParseError,
    ParsedCommunication,
    ParsedLawyer,
    ParsedRecipient,
    normalize_process_number,
    parse_communication,
)

__all__ = [
    "MAX_PER_PAGE",
    "DjenApiError",
    "DjenClient",
    "DjenConfigError",
    "DjenPage",
    "DjenParseError",
    "ParsedCommunication",
    "ParsedLawyer",
    "ParsedRecipient",
    "normalize_process_number",
    "parse_communication",
]
