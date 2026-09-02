"""Parser puro do payload do DJEN (spec 042, regras 7, 8 e 10).

Nenhum acesso a banco ou rede: entra o dict de um item de `items[]` da API, sai
um `ParsedCommunication` validado. O DJEN varia por tribunal — campo ausente ou
nulo nunca quebra o parse; campo desconhecido loga aviso e sobrevive no
`raw_payload`.
"""

import logging
from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from app.core.br_documents import strip_document_mask

logger = logging.getLogger("rito.djen")

# Chaves de primeiro nível conhecidas — mapeadas para coluna ou deliberadamente
# ignoradas por redundância (datadisponibilizacao é data_disponibilizacao em
# DD/MM/AAAA; numeroprocessocommascara é numero_processo com a máscara CNJ).
_KNOWN_FIELDS = frozenset(
    {
        "id",
        "data_disponibilizacao",
        "siglaTribunal",
        "tipoComunicacao",
        "nomeOrgao",
        "idOrgao",
        "texto",
        "numero_processo",
        "meio",
        "link",
        "tipoDocumento",
        "nomeClasse",
        "codigoClasse",
        "numeroComunicacao",
        "ativo",
        "hash",
        "status",
        "motivo_cancelamento",
        "data_cancelamento",
        "datadisponibilizacao",
        "meiocompleto",
        "numeroprocessocommascara",
        "destinatarios",
        "destinatarioadvogados",
    }
)


class DjenParseError(Exception):
    """Item sem o mínimo indispensável (id, hash ou data_disponibilizacao)."""


class ParsedRecipient(BaseModel):
    name: str
    pole: str | None = None  # 'P' (passivo) | 'A' (ativo)


class ParsedLawyer(BaseModel):
    external_lawyer_id: int | None = None
    name: str | None = None
    oab_number: str | None = None
    oab_state: str | None = None


class ParsedCommunication(BaseModel):
    external_id: int
    hash: str
    availability_date: date
    court_code: str
    communication_type: str | None = None
    document_type: str | None = None
    organ_name: str | None = None
    organ_id: int | None = None
    body: str = ""
    process_number: str | None = None
    medium: str | None = None
    medium_full: str | None = None
    class_name: str | None = None
    class_code: int | None = None
    communication_number: int | None = None
    link: str | None = None
    status: str | None = None
    is_active: bool = True
    cancellation_reason: str | None = None
    cancelled_at: date | None = None
    recipients: list[ParsedRecipient] = Field(default_factory=list)
    lawyers: list[ParsedLawyer] = Field(default_factory=list)
    # Any: raw_payload é o item bruto da API — JSON arbitrário por definição
    # (mesma justificativa do HttpResponse.json em integrations/http/types.py).
    raw_payload: dict[str, Any]


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


def _to_date(value: Any) -> date | None:
    text = _to_str(value)
    if text is None:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def normalize_process_number(value: Any) -> str | None:
    """Regra 4: numero_processo chega sem máscara e é guardado só com dígitos.
    Spec 050 (alvo/duplicação): mesmo `strip_document_mask` de `app.core.br_documents`
    usado por CPF/CNPJ — a "normalização de número de processo em um só lugar" do
    checklist é o algoritmo em si, não a assinatura (cada parser tem sua própria
    regra de None, ver `datajud/parser.py::normalize_process_number`)."""
    text = _to_str(value)
    if text is None:
        return None
    digits = strip_document_mask(text)
    return digits or None


def _parse_recipients(item: dict[str, Any]) -> list[ParsedRecipient]:
    """As partes da intimação. Entrada que não é objeto é descartada em silêncio: o DJEN
    já devolveu lista com `null` no meio, e derrubar a intimação inteira por causa de um
    destinatário malformado perderia o prazo que ela carrega."""
    return [
        ParsedRecipient(name=_to_str(r.get("nome")) or "", pole=_to_str(r.get("polo")))
        for r in item.get("destinatarios") or []
        if isinstance(r, dict)
    ]


def _parse_lawyers(item: dict[str, Any]) -> list[ParsedLawyer]:
    """Os advogados, que vêm aninhados um nível: cada entrada tem o vínculo e, dentro
    dele, o objeto `advogado`. Todo campo é opcional — é a OAB que casa a intimação com o
    escritório (spec 043), e ela às vezes vem vazia."""
    lawyers = []
    for entry in item.get("destinatarioadvogados") or []:
        if not isinstance(entry, dict):
            continue
        lawyer = entry.get("advogado") or {}
        lawyers.append(
            ParsedLawyer(
                external_lawyer_id=_to_int(entry.get("advogado_id")),
                name=_to_str(lawyer.get("nome")),
                oab_number=_to_str(lawyer.get("numero_oab")),
                oab_state=_to_str(lawyer.get("uf_oab")),
            )
        )
    return lawyers


def _communication_metadata(item: dict[str, Any]) -> dict[str, Any]:
    """Os rótulos da intimação: tribunal, órgão, classe, meio e situação.

    Todos opcionais e todos convertidos com tolerância — o DJEN varia o conjunto de campos
    entre tribunais, e um rótulo ausente não impede ninguém de ler a intimação. Os únicos
    campos que a ausência derruba (id, hash e data) ficam de fora daqui, validados por quem
    chama.

    `ativo` tem default `True`: item sem a chave é item vigente, e tratá-lo como cancelado
    esconderia uma intimação real do escritório.
    """
    return {
        "court_code": _to_str(item.get("siglaTribunal")) or "",
        "communication_type": _to_str(item.get("tipoComunicacao")),
        "document_type": _to_str(item.get("tipoDocumento")),
        "organ_name": _to_str(item.get("nomeOrgao")),
        "organ_id": _to_int(item.get("idOrgao")),
        "medium": _to_str(item.get("meio")),
        "medium_full": _to_str(item.get("meiocompleto")),
        "class_name": _to_str(item.get("nomeClasse")),
        "class_code": _to_int(item.get("codigoClasse")),
        "communication_number": _to_int(item.get("numeroComunicacao")),
        "link": _to_str(item.get("link")),
        "status": _to_str(item.get("status")),
        "is_active": bool(item.get("ativo", True)),
        "cancellation_reason": _to_str(item.get("motivo_cancelamento")),
        "cancelled_at": _to_date(item.get("data_cancelamento")),
    }


def parse_communication(item: dict[str, Any]) -> ParsedCommunication:
    unknown = sorted(set(item) - _KNOWN_FIELDS)
    if unknown:
        logger.warning("djen: campos desconhecidos no item %s: %s", item.get("id"), unknown)

    external_id = _to_int(item.get("id"))
    hash_ = _to_str(item.get("hash"))
    availability = _to_date(item.get("data_disponibilizacao"))
    if external_id is None or hash_ is None or availability is None:
        raise DjenParseError(
            f"item sem id/hash/data_disponibilizacao utilizável: id={item.get('id')!r}"
        )

    recipients = _parse_recipients(item)
    lawyers = _parse_lawyers(item)

    return ParsedCommunication(
        external_id=external_id,
        hash=hash_,
        availability_date=availability,
        body=_to_str(item.get("texto")) or "",
        process_number=normalize_process_number(item.get("numero_processo")),
        recipients=recipients,
        lawyers=lawyers,
        raw_payload=item,
        **_communication_metadata(item),
    )
