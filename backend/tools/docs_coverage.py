"""Checks that `docs/system/` keeps up with the code: no folder undocumented, no stale citation.

Two checks:

- **coverage**: every path matched by `require` (modules, packages, frontend routes) is cited
  between backticks in some documentation file. A directory counts as cited if it or any file
  inside it appears;
- **live paths**: every repository path cited between backticks exists, and every
  `tests/x.py::name` points to a `def name` in the file. Documentation that talks about a deleted
  file or a renamed test fails here.

Usage (from backend/):

    uv run python -m tools.docs_coverage

Settings in `[tool.docs-coverage]` of `backend/pyproject.toml`. Exits with 1 if it finds anything.
"""

from __future__ import annotations

import re
import subprocess
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

UNDOCUMENTED = "DOC001"
DEAD_PATH = "DOC002"
#: Raiz do repositório (o pacote está em backend/): os caminhos da documentação são desta raiz.
ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = ROOT / "backend" / "pyproject.toml"
BACKTICKED = re.compile(r"`([^`\n]+)`")
#: Names that are not project code, even when they match `require`.
IGNORED = frozenset({"__init__.py", "__pycache__", "__main__.py"})


@dataclass(frozen=True)
class Config:
    docs: Path
    require: tuple[str, ...]
    roots: tuple[str, ...]


@dataclass(frozen=True)
class Citation:
    file: Path
    line: int
    path: str
    test: str | None


def read_config() -> Config:
    with PYPROJECT.open("rb") as file:
        data: dict[str, Any] = tomllib.load(file)
    raw = data.get("tool", {}).get("docs-coverage", {})
    return Config(
        docs=ROOT / raw.get("docs", "docs/system"),
        require=tuple(raw.get("require", [])),
        roots=tuple(raw.get("roots", [])),
    )


def _citation(snippet: str, roots: tuple[str, ...]) -> tuple[str, str | None] | None:
    """`api/x.py::test` -> (`api/x.py`, `test`); what is not a repository path -> None."""
    in_repo = snippet.startswith(tuple(f"{r}/" for r in roots))
    # Globs, placeholders (`<name>`, `...`) and snippets with spaces are examples, not paths.
    if not in_repo or any(c in snippet for c in "*{<> ") or "..." in snippet:
        return None
    path, _, test = snippet.partition("::")
    path = re.sub(r":\d+$", "", path)
    return path, (test.split("[")[0] or None)


def citations(config: Config) -> Iterator[Citation]:
    for file in sorted(config.docs.rglob("*.md")):
        for number, text in enumerate(file.read_text(encoding="utf-8").splitlines(), start=1):
            for snippet in BACKTICKED.findall(text):
                found = _citation(snippet.strip(), config.roots)
                if found:
                    yield Citation(file, number, found[0], found[1])


def required(config: Config) -> Iterator[str]:
    for pattern in config.require:
        for path in sorted(ROOT.glob(pattern.rstrip("/"))):
            if path.name in IGNORED or (pattern.endswith("/") and not path.is_dir()):
                continue
            yield path.relative_to(ROOT).as_posix()


def _cited(path: str, cited: set[str]) -> bool:
    prefix = path.rstrip("/") + "/"
    return path in cited or prefix in cited or any(c.startswith(prefix) for c in cited)


def _ignored_by_git(path: str) -> bool:
    """A file that exists only on the machine (cache, capture): not missing in CI by mistake."""
    result = subprocess.run(  # noqa: S603 - fixed arguments, no shell
        ["git", "check-ignore", "-q", path],  # noqa: S607 - git from PATH, as in the Makefile
        cwd=ROOT,
        check=False,
    )
    return result.returncode == 0


def _citation_problem(citation: Citation) -> str | None:
    target = ROOT / citation.path
    if not target.exists() and not _ignored_by_git(citation.path):
        return f"cites `{citation.path}`, which does not exist"
    if citation.test and target.is_file():
        definition = re.compile(rf"^\s*(async\s+)?def {re.escape(citation.test)}\b", re.MULTILINE)
        if not definition.search(target.read_text(encoding="utf-8")):
            return f"cites the test `{citation.test}`, which does not exist in `{citation.path}`"
    return None


def check(config: Config) -> list[str]:
    everything = list(citations(config))
    cited = {c.path.rstrip("/") for c in everything} | {c.path for c in everything}
    errors = [
        f"{path}: {UNDOCUMENTED} does not appear in any file of {config.docs.relative_to(ROOT)}/"
        for path in required(config)
        if not _cited(path, cited)
    ]
    for citation in everything:
        problem = _citation_problem(citation)
        if problem:
            where = f"{citation.file.relative_to(ROOT)}:{citation.line}"
            errors.append(f"{where}: {DEAD_PATH} {problem}")
    return errors


def main() -> int:
    errors = check(read_config())
    for error in errors:
        print(error)
    if errors:
        print(f"Found {len(errors)} errors. Update docs/system/ (CLAUDE.md, Documentation).")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
