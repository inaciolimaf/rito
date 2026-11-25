# Mutation testing on the functions a change touched (mutation-testing playbook).
# Config in [tool.mutmut] and [tool.mutation] of pyproject.toml. Pin mutmut:
# this file calls its internals (_run, config(), SourceFileMutationData, get_diff_for_mutant).
"""Mutation testing on the functions a change touched, on every core, scored per tier.

Usage:

    uv run python -m tools.mutation                  # functions changed since origin/main
    uv run python -m tools.mutation --base HEAD~3    # ... since another ref
    uv run python -m tools.mutation app/x/y.py       # every function of these files
    uv run python -m tools.mutation --all --survivors s.md  # every file in scope, survivors' diffs
    uv run python -m tools.mutation --check-speed     # only the 5 s budget of the tests

Only files matching `[tool.mutation].paths` (the pure code) are mutated, and only the tests of
`[tool.mutmut]` run (the unit tests, at most `max-test-seconds` in one process). A mutant of a
function no selected test runs ("no tests") counts as a survivor: counting it as killed would score
untested code at 100%. Exit 1 when a tier scores below its minimum or the tests pass their budget.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import os
import re
import shutil
import subprocess
import sys
import tomllib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", re.MULTILINE)
MAX_SHOWN = 40
PYTEST_TIME = re.compile(r" in ([\d.]+)s")


def changed_lines(base: str, roots: list[str]) -> dict[Path, set[int]]:
    """Lines added or changed under `roots` since the merge base with `base` (worktree included)."""
    merge_base = _git("merge-base", base, "HEAD").strip()
    out: dict[Path, set[int]] = {}
    for chunk in _git("diff", "-U0", "--relative", merge_base, "--", *roots).split("\ndiff --git ")[
        1:
    ]:
        name = re.search(r"^\+\+\+ b/(\S+)$", chunk, re.MULTILINE)
        if not name or not name.group(1).endswith(".py"):
            continue
        lines = out.setdefault(Path(name.group(1)), set())
        for start, count in HUNK.findall(chunk):
            lines.update(range(int(start), int(start) + int(count or 1)))
    return out


def _git(*args: str) -> str:
    cmd = ["git", *args]  # fixed executable, arguments built here
    done = subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True)  # noqa: S603
    return done.stdout


def mutant_globs(path: Path, lines: set[int] | None) -> list[str]:
    """mutmut name patterns of the functions in `path` that overlap `lines` (all when None).

    mutmut mutates module-level functions (`x_name`) and methods (`xǁClassǁname`).
    """
    module = ".".join(path.with_suffix("").parts)
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    globs = []
    for prefix, fn in _functions(tree):
        if lines is None or lines & set(range(fn.lineno, (fn.end_lineno or fn.lineno) + 1)):
            globs.append(f"{module}.{prefix}{fn.name}__mutmut_*")
    return globs


def _functions(tree: ast.Module) -> list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    found: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            found.append(("x_", node))
        elif isinstance(node, ast.ClassDef):
            methods = [
                n for n in node.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
            ]
            found += [(f"xǁ{node.name}ǁ", m) for m in methods]
    return found


def run_mutmut(files: list[Path], globs: list[str], marker_args: list[str], workers: int) -> None:
    """Run mutmut in this process, `only_mutate` narrowed to `files` (no CLI flag for it).

    `mutants/` starts empty: mutmut treats a file it copied unmutated on an earlier run as
    "unmodified" and would skip it now that it is in `only_mutate`.
    """
    from mutmut import __main__ as main_module
    from mutmut import configuration  # mutmut is imported only when there is work to do

    os.chdir(ROOT)
    shutil.rmtree(ROOT / "mutants", ignore_errors=True)
    configuration.config().only_mutate = [str(f) for f in files]
    configuration.config().pytest_add_cli_args_test_selection += marker_args
    said = _listen_to(main_module)
    try:
        main_module._run(globs, max_children=workers)
    except SystemExit:
        # mutmut also exits when no selected test runs any mutated function; then every mutant stays
        # "not checked" and collect() counts it as "no tests". Any other exit (a test failing inside
        # mutants/, a failing clean run) is a broken run, not a score.
        if not any(line.startswith(NO_TEST_RUNS_IT) for line in said):
            raise


@dataclass(frozen=True)
class Tier:
    """A group of files held to one minimum score (`[tool.mutation].tiers`)."""

    name: str
    min_score: int
    paths: tuple[str, ...]


NO_TEST_RUNS_IT = "Stopping early, because we could not find any test case"


def _listen_to(module: object) -> list[str]:
    """Copy of what `module` prints: mutmut says why it stopped only in text."""
    said: list[str] = []

    def tee(*args: object, **kwargs: Any) -> None:
        said.append(" ".join(map(str, args)))
        print(*args, **kwargs)

    module.print = tee  # type: ignore[attr-defined]  # module globals shadow the builtin
    return said


KILLED = frozenset({"killed", "timeout", "caught by type check", "segfault"})
NOT_RUN = frozenset({"skipped", "check was interrupted by user"})


@dataclass(frozen=True)
class Mutant:
    name: str
    path: Path
    status: str  # mutmut's: killed, survived, no tests, timeout...

    @property
    def survived(self) -> bool:
        """Not caught by a test: survived, or no selected test runs its function."""
        return self.status not in KILLED


@dataclass(frozen=True)
class Settings:
    """`[tool.mutation]` in `pyproject.toml`."""

    paths: tuple[str, ...]
    test_paths: list[str]  # [tool.mutmut].pytest_add_cli_args_test_selection
    pytest_args: list[str]  # [tool.mutmut].pytest_add_cli_args (ignores, plugins off)
    roots: list[str]  # [tool.mutmut].source_paths
    test_selection: str  # a pytest -m expression; empty selects every test under test_paths
    max_test_seconds: float
    tiers: list[Tier]
    max_workers: int  # mutmut's worker processes (`max-workers`), capped below the core count

    def marker_args(self) -> list[str]:
        return ["-m", self.test_selection] if self.test_selection else []


def load_settings() -> Settings:
    with (ROOT / "pyproject.toml").open("rb") as fh:
        tool = tomllib.load(fh)["tool"]
    raw = tool["mutation"]
    mutmut = tool["mutmut"]
    tests = list(mutmut.get("pytest_add_cli_args_test_selection", ["tests/"]))
    args, roots = list(mutmut.get("pytest_add_cli_args", [])), list(mutmut["source_paths"])
    tiers = [Tier(t["name"], int(t["min-score"]), tuple(t["paths"])) for t in raw["tiers"]]
    selection, budget = raw.get("test-selection", ""), float(raw["max-test-seconds"])
    workers = min(int(raw.get("max-workers", os.cpu_count() or 1)), os.cpu_count() or 1)
    return Settings(tuple(raw["paths"]), tests, args, roots, selection, budget, tiers, workers)


def test_seconds(settings: Settings) -> float:
    """How long the tests mutmut runs take in one process, by pytest's own clock."""
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:xdist", "-p", "no:cacheprovider"]
    cmd += [
        "-o",
        "addopts=",
        *_extra(settings.pytest_args),
        *settings.marker_args(),
        *settings.test_paths,
    ]
    done = subprocess.run(  # noqa: S603
        cmd, cwd=ROOT, capture_output=True, text=True, timeout=300, check=False
    )
    last = done.stdout.strip().splitlines()[-1] if done.stdout.strip() else ""
    found = PYTEST_TIME.search(last)
    if done.returncode != 0 or not found:
        raise SystemExit(
            f"The tests mutmut runs failed:\n{done.stdout[-3000:]}{done.stderr[-2000:]}"
        )
    return float(found.group(1))


def _extra(args: list[str]) -> list[str]:
    """The mutmut pytest arguments the measure does not already pass."""
    return [a for a in args if a.startswith("--ignore") or a.startswith("--deselect")]


def check_speed(settings: Settings) -> bool:
    """True when the selected tests fit their budget; prints the measure either way."""
    took = test_seconds(settings)
    ok = took <= settings.max_test_seconds
    verdict = "ok" if ok else "OVER: make them faster or move the slow ones out of the selection"
    budget = f"{took:.2f} s of {settings.max_test_seconds:g} s"
    which = " ".join([*settings.marker_args(), *settings.test_paths])
    print(f"Tests for mutation ({which}): {budget}, {verdict}")
    return ok


def tier_of(path: Path, tiers: list[Tier]) -> Tier | None:
    """The first tier whose paths match `path` (fnmatch: `*` also crosses `/`)."""
    return next((t for t in tiers if any(fnmatch.fnmatch(str(path), p) for p in t.paths)), None)


def collect(globs: list[str]) -> list[Mutant]:
    """Every tested mutant of the functions in `globs`, read from `mutants/`."""
    from mutmut.mutation.data import SourceFileMutationData
    from mutmut.stats import status_by_exit_code
    from mutmut.utils.file_utils import walk_mutatable_files

    found = []
    for path in walk_mutatable_files():
        data = SourceFileMutationData(path=path)
        data.load()
        for name, code in data.exit_code_by_key.items():
            status = "no tests" if code is None else status_by_exit_code[code]
            if status not in NOT_RUN and _matches(name, globs):
                found.append(Mutant(name, Path(path), status))
    return found


def score(mutants: list[Mutant]) -> int:
    """Share of mutants killed, in whole percent (100 when there is nothing to kill)."""
    killed = sum(1 for m in mutants if not m.survived)
    return 100 * killed // len(mutants) if mutants else 100


def verdicts(mutants: list[Mutant], tiers: list[Tier]) -> list[tuple[Tier, int, int]]:
    """(tier, score, mutant count) of every tier that has mutants in this run."""
    out = []
    for tier in tiers:
        own = [m for m in mutants if tier_of(m.path, tiers) == tier]
        if own:
            out.append((tier, score(own), len(own)))
    return out


def report(mutants: list[Mutant], tiers: list[Tier]) -> str:
    """Markdown: score per tier against its minimum, survivors per function, the first diffs."""
    from mutmut.mutation.diff_apply import get_diff_for_mutant

    lost = [m for m in mutants if m.survived]
    untested = sum(m.status == "no tests" for m in lost)
    head = (
        f"## Mutation testing: {score(mutants)}% killed ({len(mutants) - len(lost)}/{len(mutants)})"
    )
    out = [
        head,
        "",
        f"{untested} of the {len(lost)} survivors have no test that runs their function.",
        "",
    ]
    for tier, got, count in verdicts(mutants, tiers):
        mark = "ok" if got >= tier.min_score else "BELOW"
        out.append(f"- **{tier.name}**: {got}% of {count} (minimum {tier.min_score}%) {mark}")
    per_fn = Counter(m.name.split("__mutmut_")[0] for m in lost)
    out += ["", "### Survivors per function", ""]
    out += [f"- `{fn}`: {n}" for fn, n in per_fn.most_common()]
    out += ["", f"### First {min(MAX_SHOWN, len(lost))} survivors", ""]
    for m in lost[:MAX_SHOWN]:
        out += [f"`{m.name}`", "```diff", get_diff_for_mutant(m.name, path=m.path).strip(), "```"]
    return "\n".join(out)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="*", type=Path, help="mutate every function of these files")
    parser.add_argument(
        "--base", default="origin/main", help="diff against the merge base with REF"
    )
    parser.add_argument(
        "--all", action="store_true", help="mutate every file in [tool.mutation].paths"
    )
    parser.add_argument(
        "--survivors", type=Path, help="also write every survivor's diff to this file"
    )
    parser.add_argument(
        "--check-speed", action="store_true", help="only check the tests' time budget"
    )
    return parser


def main(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    settings = load_settings()
    if not check_speed(settings):
        return 1
    if args.check_speed:
        return 0
    files = _all_files(settings.paths) if args.all else args.files
    targets = _targets(files, args.base, settings)
    globs = [g for path, lines in targets.items() for g in mutant_globs(path, lines)]
    if not globs:
        print("No function in [tool.mutation].paths changed: nothing to mutate.")
        return 0
    print(f"Mutating {len(globs)} function(s) in {len(targets)} file(s).", flush=True)
    run_mutmut(list(targets), globs, settings.marker_args(), settings.max_workers)
    mutants = collect(globs)
    if args.survivors:
        write_survivors(mutants, args.survivors)
    return _publish(mutants, settings.tiers)


def _targets(files: list[Path], base: str, settings: Settings) -> dict[Path, set[int] | None]:
    """Whole files given on the command line, or the changed lines of the files under `paths`."""
    if files:
        return dict.fromkeys(files)
    changed = changed_lines(base, settings.roots)
    return {f: lines for f, lines in changed.items() if _in_scope(f, settings.paths)}


def _in_scope(path: Path, paths: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(str(path), p) for p in paths)


def _all_files(paths: tuple[str, ...]) -> list[Path]:
    """Every Python file `[tool.mutation].paths` matches."""
    found = {
        p.relative_to(ROOT) for pattern in paths for p in ROOT.glob(pattern) if p.suffix == ".py"
    }
    return sorted(found)


def write_survivors(mutants: list[Mutant], target: Path) -> None:
    """Every survivor's diff, grouped by file: the to-do list for the missing tests."""
    from mutmut.mutation.diff_apply import get_diff_for_mutant

    out = [f"# {sum(m.survived for m in mutants)} surviving mutants of {len(mutants)}", ""]
    for m in sorted((m for m in mutants if m.survived), key=lambda m: (str(m.path), m.name)):
        tag = " (no tests)" if m.status == "no tests" else ""
        out += [
            f"## `{m.name}`{tag}",
            "```diff",
            get_diff_for_mutant(m.name, path=m.path).strip(),
            "```",
            "",
        ]
    target.write_text("\n".join(out), encoding="utf-8")


def _publish(mutants: list[Mutant], tiers: list[Tier]) -> int:
    """Print the report (and append it to the job summary); 1 when a tier is below its minimum."""
    text = report(mutants, tiers)
    print(text)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    return 1 if any(got < tier.min_score for tier, got, _ in verdicts(mutants, tiers)) else 0


def _matches(name: str, globs: list[str]) -> bool:
    return any(name.startswith(g.removesuffix("*")) for g in globs)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
