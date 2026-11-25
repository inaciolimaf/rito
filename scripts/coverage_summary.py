"""Publish the coverage measured by one CI job in the step summary (spec 117).

Usage: python3 scripts/coverage_summary.py <backend|frontend> [COV_DIR]

The floors come from coverage.json at the repository root. The reports are written before
the floor check, so this runs with `if: always()` and shows the number even when the gate
fails. Without GITHUB_STEP_SUMMARY the table goes to stdout.
"""

import json
import os
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent


def measured(path: pathlib.Path, reader) -> float | None:
    if not path.exists():
        return None
    return reader(json.loads(path.read_text()))


def render(suite: str, cov_dir: pathlib.Path) -> str:
    floors = json.loads((REPO / "coverage.json").read_text())[suite]
    if suite == "backend":
        value = measured(
            cov_dir / "backend.json", lambda d: d["totals"]["percent_covered"]
        )
        scope = "`app/` sem `workers/`"
    else:
        value = measured(
            cov_dir / "frontend" / "coverage-summary.json",
            lambda d: d["total"]["statements"]["pct"],
        )
        scope = "statements de `src/`"
    shown = "não medido" if value is None else f"{value:.2f}%"
    return "\n".join(
        [
            f"### Cobertura (spec 117) — {suite}",
            "| Suíte | Recorte | Medido | Piso |",
            "|---|---|---|---|",
            f"| {suite} | {scope} | {shown} | {floors['floor_percent']}% |",
            "",
            "Piso é piso: sobe com a medição, nunca desce sem spec própria (117, regra 7).",
            "Quando a medição subir, atualize `coverage.json` **e** os dois pisos na config.",
        ]
    )


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print(__doc__, file=sys.stderr)
        return 2
    suite = sys.argv[1]
    cov_dir = pathlib.Path(sys.argv[2] if len(sys.argv) == 3 else "/tmp/rito-cov")
    text = render(suite, cov_dir) + "\n"
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
