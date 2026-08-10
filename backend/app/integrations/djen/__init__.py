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

# DjenPublicationSource NÃO é re-exportado aqui de propósito: o módulo source
# importa o contrato PublicationSource de domain/monitored_terms/sync, que por
# sua vez importa publications/service → djen.parser → este __init__ — ciclo.
# Quem precisa do adapter importa de app.integrations.djen.source direto.

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
