"""Size lint: no function goes over the cap of useful lines, no file over its own cap.

ruff does not have these rules (`PLR0915` counts *statements*, not lines), so they live here.

A useful line is any line that is not blank, not only a comment and not part of a docstring.
Comments and docstrings are what we want to encourage; punishing them would make the rule ask for
worse code. In a function, the count goes from the body's first statement to the end: signature
and decorators stay out, their cost is already enforced by `PLR0913`.

A nested function is measured on its own *and* inside the one that contains it: a large closure
weighs on the outer function as much as any other block.

Usage:

    uv run python -m tools.function_size [path ...]

With no argument, it uses `[tool.function-size]` from `pyproject.toml`. Exits with 1 if it finds
anything. `ignore-file-temporarily` lists large files still to be split; `SIZE_STRICT=1` ignores
that list, to check how the file will end up.
"""

from __future__ import annotations

import ast
import os
import sys
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CODE = "FN001"
FILE_CODE = "FN002"
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MAX = 30
DEFAULT_FILE_MAX = 300


@dataclass(frozen=True)
class Config:
    max_lines: int
    paths: tuple[Path, ...]
    #: Files outside both rules, with the reason in `pyproject.toml` (e.g. a numba kernel, which
    #: cannot call a function inside the loop without paying a reference count per call).
    ignore: frozenset[Path] = frozenset()
    max_file_lines: int = DEFAULT_FILE_MAX
    ignore_file: frozenset[Path] = frozenset()


@dataclass(frozen=True)
class Finding:
    file: Path
    line: int
    code: str
    what: str
    useful_lines: int
    maximum: int

    def format(self) -> str:
        rel = self.file.relative_to(ROOT) if self.file.is_relative_to(ROOT) else self.file
        return (
            f"{rel}:{self.line}: {self.code} {self.what} has "
            f"{self.useful_lines} useful lines (max {self.maximum})"
        )


def read_config(argv: list[str]) -> Config:
    """Reads `[tool.function-size]`; paths on the command line take precedence."""
    raw: dict[str, Any] = {}
    pyproject = ROOT / "pyproject.toml"
    if pyproject.exists():
        with pyproject.open("rb") as file:
            data: dict[str, Any] = tomllib.load(file)
        raw = dict(data.get("tool", {}).get("function-size", {}))

    names = argv or [str(p) for p in raw.get("paths", [])] or ["."]
    strict = os.environ.get("SIZE_STRICT") == "1"
    temporary = [] if strict else raw.get("ignore-file-temporarily", [])
    return Config(
        max_lines=int(raw.get("max-lines", DEFAULT_MAX)),
        paths=tuple(ROOT / n for n in names),
        ignore=frozenset(ROOT / n for n in raw.get("ignore", [])),
        max_file_lines=int(raw.get("max-file-lines", DEFAULT_FILE_MAX)),
        ignore_file=frozenset(ROOT / n for n in temporary),
    )


def python_files(paths: tuple[Path, ...]) -> Iterator[Path]:
    for path in paths:
        if path.is_file():
            yield path
        else:
            yield from sorted(path.rglob("*.py"))


def _docstring_lines(body: list[ast.stmt]) -> set[int]:
    if not body:
        return set()
    first = body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
        and first.end_lineno is not None
    ):
        return set(range(first.lineno, first.end_lineno + 1))
    return set()


def _count(span: range, source: list[str], excluded: set[int]) -> int:
    useful = 0
    for number in span:
        text = source[number - 1].strip()
        if number not in excluded and text and not text.startswith("#"):
            useful += 1
    return useful


def measure(node: ast.FunctionDef | ast.AsyncFunctionDef, source: list[str]) -> int:
    """How many useful lines the body of `node` takes."""
    docstring = _docstring_lines(node.body)
    body = [s for s in node.body if s.lineno not in docstring]
    if not body or node.end_lineno is None:
        return 0
    return _count(range(body[0].lineno, node.end_lineno + 1), source, docstring)


def measure_file(tree: ast.Module, source: list[str]) -> int:
    """Useful lines of the whole file, without module, class and function docstrings."""
    docstrings = _docstring_lines(tree.body)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            docstrings |= _docstring_lines(node.body)
    return _count(range(1, len(source) + 1), source, docstrings)


def _file_findings(
    file: Path, tree: ast.Module, lines: list[str], config: Config
) -> Iterator[Finding]:
    if file in config.ignore_file:
        return
    total = measure_file(tree, lines)
    if total > config.max_file_lines:
        yield Finding(file, 1, FILE_CODE, "the file", total, config.max_file_lines)


def _function_findings(
    file: Path, tree: ast.Module, lines: list[str], config: Config
) -> Iterator[Finding]:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            useful = measure(node, lines)
            if useful > config.max_lines:
                yield Finding(file, node.lineno, CODE, f"`{node.name}`", useful, config.max_lines)


def analyze(file: Path, config: Config) -> Iterator[Finding]:
    source = file.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(file))
    except SyntaxError as error:  # a broken file is ruff's problem, not this tool's
        print(f"{file}: {CODE} could not be analyzed ({error})", file=sys.stderr)
        return
    lines = source.splitlines()
    yield from _file_findings(file, tree, lines, config)
    yield from _function_findings(file, tree, lines, config)


def main(argv: list[str] | None = None) -> int:
    config = read_config(list(argv if argv is not None else sys.argv[1:]))
    findings = [
        finding
        for file in python_files(config.paths)
        if file not in config.ignore
        for finding in analyze(file, config)
    ]
    for finding in sorted(findings, key=lambda f: (f.code, -f.useful_lines, str(f.file))):
        print(finding.format())
    if findings:
        print(f"Found {len(findings)} errors.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
