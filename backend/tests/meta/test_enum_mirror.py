"""Dívida nº 15 (fechada na spec 101, regra 22): enums do backend espelhados à mão em TS.

A dívida não era o espelho — era o espelho **sem alarme**: `PartyPoleApi` e cia. são
unions escritos à mão em `frontend/src/features/*/api.ts` que podiam ganhar (ou perder)
um valor em relação ao StrEnum do backend sem nada reclamar, até alguém ver um select
vazio em produção.

Dois testes, duas metades do alarme:
1. o arquivo GERADO commitado está em sincronia com os StrEnum de hoje;
2. nenhum union escrito à mão diverge do StrEnum de mesmo nome.

O (2) é o que realmente fecha a dívida: migrar os 36 unions para importar do arquivo
gerado é refactor de front, fora do escopo da 101 (§3) — o alarme não é.
"""

import re
from pathlib import Path

from scripts.dump_enums import collect_api_enums, render

_FRONTEND = Path(__file__).resolve().parents[3] / "frontend" / "src"
_GENERATED = _FRONTEND / "lib" / "domainEnums.generated.ts"

# `export type Nome = "A" | "B";` num arquivo só (unions de string literal, nada mais).
_UNION = re.compile(r"^export type (\w+) =\s*((?:\s*\|?\s*\"[^\"]*\")+)\s*;", re.MULTILINE)


def test_arquivo_gerado_esta_em_sincronia() -> None:
    """Regenerar não pode produzir diff — senão o arquivo commitado já é mentira."""
    assert _GENERATED.exists(), "rode `uv run python -m scripts.dump_enums`"
    assert _GENERATED.read_text(encoding="utf-8") == render(collect_api_enums()), (
        "domainEnums.generated.ts está desatualizado — "
        "rode `cd backend && uv run python -m scripts.dump_enums`"
    )


def test_nenhum_union_escrito_a_mao_diverge_do_backend() -> None:
    """O alarme da dívida nº 15. Compara por NOME: um union TS chamado `PartyPole` ou
    `PartyPoleApi` tem que ter exatamente os valores do StrEnum `PartyPole`.

    Union cujo nome não casa com nenhum StrEnum é ignorado — há muitos unions no front
    que são de UI (`"asc" | "desc"`), não espelho de enum de domínio.
    """
    backend = {
        name: {member.value for member in enum} for name, enum in collect_api_enums().items()
    }
    divergentes: list[str] = []

    for arquivo in sorted(_FRONTEND.rglob("*.ts")):
        if arquivo == _GENERATED:
            continue
        for nome, corpo in _UNION.findall(arquivo.read_text(encoding="utf-8")):
            alvo = nome[:-3] if nome.endswith("Api") and nome[:-3] in backend else nome
            if alvo not in backend:
                continue
            valores = set(re.findall(r'"([^"]*)"', corpo))
            if valores != backend[alvo]:
                faltando = backend[alvo] - valores
                sobrando = valores - backend[alvo]
                divergentes.append(
                    f"{arquivo.relative_to(_FRONTEND)}: {nome} divergiu de {alvo} "
                    f"(faltando no TS: {sorted(faltando) or '—'}; "
                    f"não existe no backend: {sorted(sobrando) or '—'})"
                )

    assert not divergentes, "unions TS fora de sincronia com o backend:\n" + "\n".join(divergentes)
