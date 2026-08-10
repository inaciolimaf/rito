"""Parser do DJEN contra as fixtures reais capturadas (spec 042, §8).

As fixtures vivem em tests/fixtures/http/comunicaapi.pje.jus.br/ — ver o README.md
do diretório para a proveniência de cada uma.
"""

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.integrations.djen.parser import (
    DjenParseError,
    normalize_process_number,
    parse_communication,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "http" / "comunicaapi.pje.jus.br"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


async def test_parse_fiel_contra_fixture_real() -> None:
    """Cada campo mapeado confere, item a item, com a captura real (OAB/MG)."""
    payload = load_fixture("oab_mg.json")
    assert payload["items"], "fixture sem itens — a captura precisa ser refeita"

    for raw in payload["items"]:
        parsed = parse_communication(raw)

        assert parsed.external_id == int(raw["id"])
        assert parsed.hash == raw["hash"]
        assert parsed.availability_date == date.fromisoformat(raw["data_disponibilizacao"])
        assert parsed.court_code == raw["siglaTribunal"]
        assert parsed.communication_type == raw["tipoComunicacao"]
        assert parsed.organ_name == raw["nomeOrgao"]
        # A API manda idOrgao/codigoClasse/numeroComunicacao como STRING ("202") —
        # o parser normaliza para int, então a comparação fiel coage o bruto.
        assert parsed.organ_id == int(raw["idOrgao"])
        assert parsed.body == raw["texto"]
        assert parsed.process_number == raw["numero_processo"]
        assert parsed.medium == raw["meio"]
        assert parsed.medium_full == raw["meiocompleto"]
        assert parsed.class_name == raw["nomeClasse"]
        assert parsed.class_code == int(raw["codigoClasse"])
        assert parsed.communication_number == int(raw["numeroComunicacao"])
        assert parsed.status == raw["status"]
        assert parsed.is_active == raw["ativo"]
        assert parsed.raw_payload == raw  # pydantic copia — identidade não, igualdade sim

        assert len(parsed.recipients) == len(raw["destinatarios"])
        for parsed_recipient, raw_recipient in zip(
            parsed.recipients, raw["destinatarios"], strict=True
        ):
            assert parsed_recipient.name == raw_recipient["nome"]
            assert parsed_recipient.pole == raw_recipient["polo"]

        assert len(parsed.lawyers) == len(raw["destinatarioadvogados"])
        for parsed_lawyer, raw_lawyer in zip(
            parsed.lawyers, raw["destinatarioadvogados"], strict=True
        ):
            assert parsed_lawyer.external_lawyer_id == raw_lawyer["advogado_id"]
            assert parsed_lawyer.name == raw_lawyer["advogado"]["nome"]
            assert parsed_lawyer.oab_number == raw_lawyer["advogado"]["numero_oab"]
            assert parsed_lawyer.oab_state == raw_lawyer["advogado"]["uf_oab"]


async def test_parse_fixture_trabalhista() -> None:
    """TRT2: mesma estrutura, tribunal trabalhista — o parse não é por tribunal."""
    payload = load_fixture("trt2.json")
    parsed = [parse_communication(item) for item in payload["items"]]

    assert len(parsed) == len(payload["items"])
    assert all(item.court_code == "TRT2" for item in parsed)


async def test_parse_publicacao_cancelada() -> None:
    """Fixture derivada (ver README do diretório): anulada carrega status/motivo/data."""
    payload = load_fixture("cancelada.json")
    parsed = parse_communication(payload["items"][0])

    assert parsed.status == "C"
    assert parsed.is_active is False
    assert parsed.cancellation_reason == "Publicação anulada a pedido da parte."
    assert parsed.cancelled_at == date(2026, 8, 8)


async def test_campos_nulos_ou_ausentes_nao_quebram() -> None:
    """Regra 7: o DJEN varia por tribunal — só id, hash e data são indispensáveis."""
    parsed = parse_communication(
        {
            "id": 1,
            "hash": "abc",
            "data_disponibilizacao": "2026-08-07",
            "siglaTribunal": "TJSP",
            "texto": None,
            "numero_processo": None,
            "destinatarios": None,
            "destinatarioadvogados": None,
            "codigoClasse": "",
            "motivo_cancelamento": None,
        }
    )

    assert parsed.body == ""
    assert parsed.process_number is None
    assert parsed.recipients == []
    assert parsed.lawyers == []
    assert parsed.class_code is None
    assert parsed.cancellation_reason is None


async def test_item_sem_minimo_indispensavel_levanta_parse_error() -> None:
    with pytest.raises(DjenParseError):
        parse_communication({"id": 1, "siglaTribunal": "TJSP"})


async def test_campo_desconhecido_loga_aviso_e_sobrevive_no_raw(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Regra 8: campo novo da API não quebra o parse — avisa e fica no raw_payload."""
    with caplog.at_level(logging.WARNING, logger="rito.djen"):
        parsed = parse_communication(
            {
                "id": 7,
                "hash": "h",
                "data_disponibilizacao": "2026-08-07",
                "siglaTribunal": "TJSP",
                "campo_novo_da_api": {"valor": 42},
            }
        )

    assert parsed.raw_payload["campo_novo_da_api"] == {"valor": 42}
    assert any("campo_novo_da_api" in record.message for record in caplog.records)


async def test_numero_processo_normalizado_para_digitos() -> None:
    """Regra 4: mesmo que venha com máscara, só dígitos sobrevivem."""
    assert normalize_process_number("2873042-75.2023.8.13.0000") == "28730427520238130000"
    assert normalize_process_number("  ") is None
    assert normalize_process_number(None) is None
