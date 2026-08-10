"""Parser puro do `_source` do DataJud (spec 046, §7 regra 10).

Nenhum acesso a banco ou rede: entra o `_source` de um hit da busca
Elasticsearch, sai um `ParsedProcess` validado. Campo de primeiro nível
desconhecido loga aviso e sobrevive em `raw_source` — mesmo padrão do parser
do DJEN (spec 042). Descarte por sigilo (regra 6) e aviso de código de
movimento desconhecido (regra 7) exigem consulta ao banco — ficam no
`DatajudService`, não aqui.
"""

import logging
import re
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("rito.datajud")

_NON_DIGITS = re.compile(r"\D")

# Chaves de primeiro nível do `_source` conhecidas (Anexo I do tutorial oficial
# da API Pública do Datajud, DPJ/CNJ).
_KNOWN_FIELDS = frozenset(
    {
        "id",
        "tribunal",
        "grau",
        "numeroProcesso",
        "dataAjuizamento",
        "nivelSigilo",
        "formato",
        "sistema",
        "classe",
        "assuntos",
        "orgaoJulgador",
        "movimentos",
        "dataHoraUltimaAtualizacao",
        "@timestamp",
    }
)


class DatajudParseError(Exception):
    """`_source` sem o mínimo indispensável (id ou numeroProcesso)."""


class ParsedMovementComplement(BaseModel):
    code: int | None = None
    description: str | None = None
    value: int | None = None
    name: str | None = None


class ParsedMovement(BaseModel):
    code: int
    name: str
    occurred_at: datetime | None = None
    complements: list[ParsedMovementComplement] = Field(default_factory=list)
    organ_code: str | None = None
    organ_name: str | None = None


class ParsedSubject(BaseModel):
    code: int | None = None
    name: str | None = None


class ParsedProcess(BaseModel):
    external_id: str
    court_code: str
    degree: str | None = None
    process_number: str
    filed_at: datetime | None = None
    secrecy_level: int = 0
    class_code: int | None = None
    class_name: str | None = None
    system_code: int | None = None
    system_name: str | None = None
    format_code: int | None = None
    format_name: str | None = None
    organ_code: int | None = None
    organ_name: str | None = None
    organ_municipality_ibge: int | None = None
    last_updated_at: datetime | None = None
    subjects: list[ParsedSubject] = Field(default_factory=list)
    movements: list[ParsedMovement] = Field(default_factory=list)
    # Any: `_source` bruto do Elasticsearch — JSON arbitrário por definição
    # (mesma justificativa do ParsedCommunication.raw_payload do DJEN).
    raw_source: dict[str, Any]


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_datetime(value: Any) -> datetime | None:
    """ISO 8601 com sufixo `Z` (movimentos, dataHoraUltimaAtualizacao)."""
    text = _to_str(value)
    if text is None:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _to_compact_datetime(value: Any) -> datetime | None:
    """`dataAjuizamento` chega como `AAAAMMDDHHmmss`, não ISO (regra própria do
    Datajud, fora do padrão usado no resto do payload)."""
    text = _to_str(value)
    if text is None or len(text) != 14 or not text.isdigit():
        return None
    try:
        return datetime.strptime(text, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def normalize_process_number(value: Any) -> str:
    text = _to_str(value) or ""
    return _NON_DIGITS.sub("", text)


def _parse_movement(item: dict[str, Any]) -> ParsedMovement | None:
    code = _to_int(item.get("codigo"))
    name = _to_str(item.get("nome"))
    if code is None or name is None:
        return None
    organ = item.get("orgaoJulgador") or {}
    complements = [
        ParsedMovementComplement(
            code=_to_int(complement.get("codigo")),
            description=_to_str(complement.get("descricao")),
            value=_to_int(complement.get("valor")),
            name=_to_str(complement.get("nome")),
        )
        for complement in item.get("complementosTabelados") or []
        if isinstance(complement, dict)
    ]
    return ParsedMovement(
        code=code,
        name=name,
        occurred_at=_to_datetime(item.get("dataHora")),
        complements=complements,
        organ_code=_to_str(organ.get("codigoOrgao")),
        organ_name=_to_str(organ.get("nomeOrgao")),
    )


def parse_process(source: dict[str, Any]) -> ParsedProcess:
    unknown = sorted(set(source) - _KNOWN_FIELDS)
    if unknown:
        logger.warning("datajud: campos desconhecidos em %s: %s", source.get("id"), unknown)

    external_id = _to_str(source.get("id"))
    process_number = normalize_process_number(source.get("numeroProcesso"))
    if external_id is None or not process_number:
        raise DatajudParseError(f"_source sem id/numeroProcesso utilizável: {source.get('id')!r}")

    classe = source.get("classe") or {}
    sistema = source.get("sistema") or {}
    formato = source.get("formato") or {}
    orgao = source.get("orgaoJulgador") or {}

    subjects = [
        ParsedSubject(code=_to_int(item.get("codigo")), name=_to_str(item.get("nome")))
        for item in source.get("assuntos") or []
        if isinstance(item, dict)
    ]
    movements = [
        movement
        for item in source.get("movimentos") or []
        if isinstance(item, dict) and (movement := _parse_movement(item)) is not None
    ]

    return ParsedProcess(
        external_id=external_id,
        court_code=_to_str(source.get("tribunal")) or "",
        degree=_to_str(source.get("grau")),
        process_number=process_number,
        filed_at=_to_compact_datetime(source.get("dataAjuizamento")),
        secrecy_level=_to_int(source.get("nivelSigilo")) or 0,
        class_code=_to_int(classe.get("codigo")),
        class_name=_to_str(classe.get("nome")),
        system_code=_to_int(sistema.get("codigo")),
        system_name=_to_str(sistema.get("nome")),
        format_code=_to_int(formato.get("codigo")),
        format_name=_to_str(formato.get("nome")),
        organ_code=_to_int(orgao.get("codigo")),
        organ_name=_to_str(orgao.get("nome")),
        organ_municipality_ibge=_to_int(orgao.get("codigoMunicipioIBGE")),
        last_updated_at=_to_datetime(source.get("dataHoraUltimaAtualizacao")),
        subjects=subjects,
        movements=movements,
        raw_source=source,
    )
