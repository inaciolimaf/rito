"""Parser do DataJud contra a fixture real capturada (spec 046, §8).

As fixtures vivem em tests/fixtures/http/api-publica.datajud.cnj.jus.br/ — ver
o README.md do diretório para a proveniência de cada uma.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.integrations.datajud.parser import parse_process

FIXTURES = (
    Path(__file__).resolve().parents[1] / "fixtures" / "http" / "api-publica.datajud.cnj.jus.br"
)


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_parse_fiel_contra_fixture_real() -> None:
    """Cada campo mapeado confere, item a item, com a captura real (TJSP)."""
    payload = load_fixture("tjsp_processo.json")
    hits = payload["hits"]["hits"]
    assert hits, "fixture sem hits — a captura precisa ser refeita"

    for hit in hits:
        source = hit["_source"]
        parsed = parse_process(source)

        assert parsed.external_id == source["id"]
        assert parsed.court_code == source["tribunal"]
        assert parsed.degree == source["grau"]
        assert parsed.process_number == source["numeroProcesso"]
        assert parsed.secrecy_level == source["nivelSigilo"]
        assert parsed.class_code == source["classe"]["codigo"]
        assert parsed.class_name == source["classe"]["nome"]
        assert parsed.system_code == source["sistema"]["codigo"]
        assert parsed.system_name == source["sistema"]["nome"]
        assert parsed.format_code == source["formato"]["codigo"]
        assert parsed.format_name == source["formato"]["nome"]
        assert parsed.organ_code == source["orgaoJulgador"]["codigo"]
        assert parsed.organ_name == source["orgaoJulgador"]["nome"]
        assert parsed.organ_municipality_ibge == source["orgaoJulgador"]["codigoMunicipioIBGE"]
        assert parsed.raw_source == source

        assert len(parsed.subjects) == len(source["assuntos"])
        for parsed_subject, raw_subject in zip(parsed.subjects, source["assuntos"], strict=True):
            assert parsed_subject.code == raw_subject["codigo"]
            assert parsed_subject.name == raw_subject["nome"]

        assert len(parsed.movements) == len(source["movimentos"])
        for parsed_movement, raw_movement in zip(
            parsed.movements, source["movimentos"], strict=True
        ):
            assert parsed_movement.code == raw_movement["codigo"]
            assert parsed_movement.name == raw_movement["nome"]
            assert parsed_movement.occurred_at == datetime.fromisoformat(
                raw_movement["dataHora"].replace("Z", "+00:00")
            )


def test_dataajuizamento_no_formato_compacto_datajud() -> None:
    """`dataAjuizamento` chega como AAAAMMDDHHmmss, fora do padrão ISO do resto
    do payload — descoberta registrada na spec 046."""
    payload = load_fixture("tjsp_processo.json")
    source = payload["hits"]["hits"][0]["_source"]
    parsed = parse_process(source)

    raw = source["dataAjuizamento"]
    expected = datetime.strptime(raw, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    assert parsed.filed_at == expected


def test_parse_de_movimentos_com_complementos_tabelados() -> None:
    """Regra do glossário: `complementosTabelados[]` vira uma lista tipada, com
    `codigo`/`descricao`/`valor`/`nome` preservados."""
    payload = load_fixture("tjsp_processo.json")
    source = payload["hits"]["hits"][1]["_source"]  # grau JE tem complementos
    parsed = parse_process(source)

    with_complements = [m for m in parsed.movements if m.complements]
    raw_with_complements = [m for m in source["movimentos"] if m.get("complementosTabelados")]
    assert with_complements, "fixture sem movimento com complementosTabelados"
    assert len(with_complements) == len(raw_with_complements)

    parsed_movement = with_complements[0]
    raw_movement = raw_with_complements[0]
    assert len(parsed_movement.complements) == len(raw_movement["complementosTabelados"])
    parsed_complement = parsed_movement.complements[0]
    raw_complement = raw_movement["complementosTabelados"][0]
    assert parsed_complement.code == raw_complement["codigo"]
    assert parsed_complement.description == raw_complement["descricao"]
    assert parsed_complement.value == raw_complement["valor"]
    assert parsed_complement.name == raw_complement["nome"]
