"""Guarda-corpo de citação inventada (spec 087, regra 6).

Súmula que não existe é o erro mais caro que um agente jurídico pode cometer: o número
parece número, passa por uma revisão apressada e chega ao tribunal.
"""

from app.domain.legal_agents.citations import (
    REMOVED_MARKER,
    find_citations,
    strip_unsupported_citations,
)

CONTEXTO = (
    "Processo 0001234-56.2026.8.26.0100. O autor juntou decisão que cita a Súmula 297 "
    "do TST. Não há outras referências."
)


def test_citacao_que_esta_no_contexto_permanece() -> None:
    texto = "<p>Aplica-se a Súmula 297 do TST ao caso.</p>"

    resultado, removidas = strip_unsupported_citations(texto, CONTEXTO)

    assert resultado == texto
    assert removidas == []


def test_citacao_inventada_e_removida_e_registrada() -> None:
    texto = "<p>Conforme a Súmula 331 do TST e o REsp 1.234.567/SP, o pedido procede.</p>"

    resultado, removidas = strip_unsupported_citations(texto, CONTEXTO)

    assert REMOVED_MARKER in resultado
    assert "Súmula 331" not in resultado
    assert "1.234.567" not in resultado
    assert {item["kind"] for item in removidas} == {"súmula", "recurso"}


def test_numero_de_processo_alheio_nao_passa() -> None:
    texto = "<p>Nos autos 9999999-11.2020.8.26.0500 já se decidiu assim.</p>"

    resultado, removidas = strip_unsupported_citations(texto, CONTEXTO)

    assert REMOVED_MARKER in resultado
    assert removidas[0]["kind"] == "processo"


def test_o_processo_do_proprio_caso_permanece() -> None:
    texto = "<p>Nos autos 0001234-56.2026.8.26.0100, o autor requer…</p>"

    resultado, _removidas = strip_unsupported_citations(texto, CONTEXTO)

    assert "0001234-56.2026.8.26.0100" in resultado


def test_encontra_as_formas_comuns_de_citacao() -> None:
    achadas = find_citations(
        "<p>Súmula Vinculante nº 10, REsp 1.111.111, AgRg 2.222.222 e "
        "0001234-56.2026.8.26.0100.</p>"
    )

    assert {item.kind for item in achadas} == {"súmula", "recurso", "processo"}
