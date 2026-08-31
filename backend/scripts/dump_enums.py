"""Gera os union types TypeScript a partir dos StrEnum de domínio (spec 101, regra 22).

Fecha a **dívida nº 15**. O gatilho registrado nela era "quando o 4º enum de domínio
cruzar a fronteira da API"; a contagem feita na 101 achou **16**, muito além do limite —
a decisão é do número, não do gosto.

O que a dívida cobra não é o arquivo gerado, é o **alarme**: os unions escritos à mão em
`frontend/src/features/*/api.ts` podiam divergir do StrEnum do backend sem nada
reclamar. Quem garante isso é `tests/meta/test_enum_mirror.py`, que roda este módulo e
compara. Este script é a fonte; o teste é o alarme.

Uso:
    uv run python -m scripts.dump_enums          # escreve o arquivo gerado
    uv run python -m scripts.dump_enums --check  # falha se o commitado está desatualizado
"""

from __future__ import annotations

import argparse
import importlib
import pkgutil
import sys
from enum import StrEnum
from pathlib import Path
from typing import Any, get_args

from pydantic import BaseModel

_HEADER = """\
// GERADO por backend/scripts/dump_enums.py — não edite à mão.
// Fonte de verdade: os StrEnum de `backend/app/domain/**`. Regenerar:
//   cd backend && uv run python -m scripts.dump_enums
// O meta-teste `tests/meta/test_enum_mirror.py` falha se este arquivo sair de sincronia.
"""

_FRONTEND_LIB = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib"
_OUTPUT = _FRONTEND_LIB / "domainEnums.generated.ts"


def _iter_schema_modules() -> list[Any]:
    """Todo `app/domain/<ctx>/schemas.py` — é lá que está a fronteira da API."""
    import app.domain

    modules = []
    for info in pkgutil.iter_modules(app.domain.__path__):
        try:
            modules.append(importlib.import_module(f"app.domain.{info.name}.schemas"))
        except ModuleNotFoundError:
            # Nem todo bounded context expõe schemas (ex.: pacotes só de modelos).
            continue
    return modules


def _enums_in_annotation(annotation: Any) -> list[type[StrEnum]]:
    """Desembrulha `X | None`, `list[X]`, `Literal[...]` etc. atrás do tipo do campo."""
    found: list[type[StrEnum]] = []
    if isinstance(annotation, type) and issubclass(annotation, StrEnum):
        found.append(annotation)
    for arg in get_args(annotation):
        found.extend(_enums_in_annotation(arg))
    return found


def collect_api_enums() -> dict[str, type[StrEnum]]:
    """Os StrEnum que aparecem em algum campo de algum schema Pydantic — ou seja, os que
    de fato cruzam a fronteira da API. Um StrEnum usado só internamente não gera TS."""
    found: dict[str, type[StrEnum]] = {}
    for module in _iter_schema_modules():
        for obj in vars(module).values():
            if not (isinstance(obj, type) and issubclass(obj, BaseModel)):
                continue
            for field in obj.model_fields.values():
                for enum_type in _enums_in_annotation(field.annotation):
                    found[enum_type.__name__] = enum_type
    return dict(sorted(found.items()))


def render(enums: dict[str, type[StrEnum]]) -> str:
    lines = [_HEADER]
    for name, enum_type in enums.items():
        members = " | ".join(f'"{member.value}"' for member in enum_type)
        lines.append(f"export type {name} = {members};\n")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="só verifica, não escreve")
    args = parser.parse_args()

    content = render(collect_api_enums())
    if args.check:
        current = _OUTPUT.read_text(encoding="utf-8") if _OUTPUT.exists() else ""
        if current != content:
            print(f"{_OUTPUT} desatualizado — rode `uv run python -m scripts.dump_enums`.")
            return 1
        return 0

    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _OUTPUT.write_text(content, encoding="utf-8")
    print(f"{_OUTPUT} atualizado com {len(collect_api_enums())} enums.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
