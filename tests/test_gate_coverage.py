"""The quality gate must cover every Python source root — including ones added later.

CLEAN-2: ``api/`` was missing from the Makefile's ``SRC_DIRS``, so ruff never ran over the
FastAPI layer — every route and every wire DTO, i.e. the files where the contract lives.
The gate had a hole exactly where the contract lives.

Three hand-maintained lists decide a source root's fate, and ``api`` had fallen out of two:
``SRC_DIRS`` (what ruff and mypy check), ``[tool.setuptools.packages.find].include`` (which
packages an installed build contains) and ``[tool.setuptools] py-modules`` (which top-level
modules it contains). A hand-maintained list drifts in silence; these tests make it drift
loudly instead.

The discovery rule is deliberately **"a directory holding Python source"**, NOT "a directory
holding an ``__init__.py``". Keying on ``__init__.py`` would let a namespace package (no
``__init__.py``) be born ungated and invisible — re-creating this very bug under a green
test. Likewise the packaging check asks setuptools what it would actually ship, rather than
re-reading ``include`` — an ``exclude`` entry can drop a package that ``include`` names.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

from setuptools import find_packages

REPO_ROOT = Path(__file__).resolve().parents[1]

# Vendored, generated, or local-environment trees — not our source, never gated.
PRUNED_DIRS: frozenset[str] = frozenset(
    {"node_modules", "__pycache__", "dist", "build", "venv", "env", ".tox", "site-packages"}
)

# Source roots deliberately left out of the gate. Empty on purpose: an exemption must show
# up as a visible diff with a reason, never as a silent skip.
ALLOWED_UNGATED: frozenset[str] = frozenset()

# Gated by ruff/mypy, but not shipped in an installed build.
NOT_DISTRIBUTED: frozenset[str] = frozenset({"tests"})

# Build/test scaffolding: linted like everything else, but it is not a distributable module.
# Demanding these appear in `py-modules` would tell the author to ship pytest plumbing in
# the wheel, which is wrong.
NOT_DISTRIBUTED_MODULES: frozenset[str] = frozenset({"conftest", "setup", "noxfile", "tasks"})


def _holds_python(root: Path) -> bool:
    """Does this tree hold Python source anywhere, ignoring vendored/generated dirs?

    The search is DEEP on purpose. A shallow "*.py directly inside" check misses a root
    whose Python starts one level down (``<root>/core/thing.py``) — that root is then never
    discovered, never demanded in SRC_DIRS, and never linted: CLEAN-2 all over again, under
    a green test.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name
            for name in dirnames
            if name not in PRUNED_DIRS
            and not name.startswith(".")
            and not name.endswith(".egg-info")
        ]
        del dirpath
        if any(name.endswith(".py") for name in filenames):
            return True
    return False


def _source_dirs() -> set[str]:
    """Every top-level directory holding Python source, at any depth."""
    return {
        path.name
        for path in REPO_ROOT.iterdir()
        if path.is_dir()
        and not path.name.startswith(".")
        and not path.name.endswith(".egg-info")
        and path.name not in PRUNED_DIRS
        and _holds_python(path)
    }


def _source_modules() -> set[str]:
    """Every top-level Python module (``config.py``, ``schema.py``, ``main.py``)."""
    return {path.stem for path in REPO_ROOT.glob("*.py")}


def _src_dirs_raw() -> list[str]:
    """The raw SRC_DIRS entries, as ruff and mypy receive them on the command line."""
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    matches = re.findall(r"^SRC_DIRS\s*[:?+]?=\s*(.+)$", makefile, re.MULTILINE)
    assert matches, "No SRC_DIRS assignment in the Makefile — was it renamed?"
    # A later re-assignment silently wins in make. One list, or the parse below is a lie.
    assert len(matches) == 1, f"SRC_DIRS is assigned {len(matches)} times — make uses the last"
    entries: list[str] = matches[0].split()
    return entries


def _src_dirs() -> set[str]:
    """The SRC_DIRS list that ``make lint`` and ``make typecheck`` hand to ruff and mypy."""
    return {entry.rstrip("/").removesuffix(".py") for entry in _src_dirs_raw()}


def _gate_recipes() -> str:
    """The bodies of the `lint` and `typecheck` targets."""
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    bodies = re.findall(r"^(?:lint|typecheck):.*\n((?:\t.*\n)+)", makefile, re.MULTILINE)
    assert len(bodies) == 2, f"Expected `lint` and `typecheck` targets, found {len(bodies)}"
    joined: str = "".join(bodies)
    return joined


def _setuptools_config() -> dict[str, Any]:
    pyproject: dict[str, Any] = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    config: dict[str, Any] = pyproject["tool"]["setuptools"]
    return config


def _distributed_packages() -> set[str]:
    """The packages an installed build actually contains.

    Resolved through setuptools itself, so an ``exclude`` entry cannot quietly drop a
    package that ``include`` appears to name.
    """
    find = _setuptools_config()["packages"]["find"]
    # `where` must be honoured, not assumed: pointing it at a directory that does not exist
    # ships NOTHING, and a guard that keeps scanning the repo root would report every
    # package as present while the real build is empty.
    where = find.get("where", ["."])
    found: list[str] = []
    for root in where:
        found += find_packages(
            where=str(REPO_ROOT / root),
            include=find.get("include", ("*",)),
            exclude=find.get("exclude", ()),
        )
    return {name.split(".")[0] for name in found}


def _distributed_modules() -> set[str]:
    modules: list[str] = _setuptools_config()["py-modules"]
    return set(modules)


def test_the_parsers_are_not_vacuous() -> None:
    """Guard the guard: a reformatted Makefile must not quietly yield an empty list.

    Without this, a rename or a line-continuation makes the regex match nothing, every
    other assertion below passes over an empty set, and the gate hole reopens undetected.
    """
    assert "tests" in _src_dirs(), "SRC_DIRS parsed to something wrong — the regex is stale"
    assert "config" in _src_dirs(), "SRC_DIRS parse is dropping top-level modules"
    assert "web" in _distributed_packages(), "pyproject's package list parsed to something wrong"
    assert "config" in _distributed_modules(), "pyproject's py-modules parsed to something wrong"
    assert _source_dirs() >= {"api", "web"}, "source-root discovery is not finding the repo"
    assert _source_modules() >= {"config"}, "module discovery is not finding the repo"


def test_the_gate_targets_actually_use_src_dirs() -> None:
    """A perfect SRC_DIRS is worthless if the recipe that runs ruff ignores it.

    Every assertion in this file reasons about SRC_DIRS. If `lint:` hardcoded its own list
    of directories, SRC_DIRS could name every package on disk while ruff checked a subset —
    CLEAN-2 again, one layer up, with this file's tests all green.
    """
    recipes = _gate_recipes()
    assert recipes.count("$(SRC_DIRS)") == 2, (
        "`lint` and `typecheck` must both run over $(SRC_DIRS). One of them is using a "
        "hardcoded path list, so what this file checks is not what the gate checks."
    )


def test_the_linters_do_not_exclude_a_source_root() -> None:
    """Ask ruff what it would actually check — don't trust the config to be honest.

    Today an `extend-exclude` cannot hide a source root, because ruff ignores exclusions for
    paths named explicitly on the command line and `make lint` names them (verified: a real
    error in an "excluded" api/ is still caught). But `force-exclude = true` — a stock
    setting, and what pre-commit users reach for — flips exactly that, at which point a
    one-line pyproject edit could silently drop this layer again while SRC_DIRS still names
    it. This test asks the tool what it would really check, so that edit fails loudly.
    """
    completed = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--show-files", *_src_dirs_raw()],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    checked = {
        Path(line).resolve().relative_to(REPO_ROOT).parts[0]
        for line in completed.stdout.splitlines()
        if line.strip()
    }
    assert checked, f"ruff reported no files at all: {completed.stderr.strip()}"
    skipped = (_source_dirs() | _source_modules()) - {name.removesuffix(".py") for name in checked}
    assert not skipped, (
        f"ruff would not check {sorted(skipped)} even though SRC_DIRS names them — an "
        f"`exclude` / `extend-exclude` in pyproject.toml is overriding the gate."
    )


def test_every_source_root_is_linted_and_typechecked() -> None:
    gated = _src_dirs()
    missing = (_source_dirs() | _source_modules()) - gated - ALLOWED_UNGATED
    assert not missing, (
        f"{sorted(missing)} are absent from the Makefile's SRC_DIRS, so `make check` never "
        f"lints or typechecks them. Add them to SRC_DIRS — or, if that is deliberate, to "
        f"ALLOWED_UNGATED with a reason."
    )


def test_every_source_root_is_distributed() -> None:
    missing = _source_dirs() - _distributed_packages() - NOT_DISTRIBUTED
    assert not missing, (
        f"{sorted(missing)} are missing from an installed build. Add them to "
        f"[tool.setuptools.packages.find].include in pyproject.toml (a package also needs an "
        f"__init__.py to be shipped at all), or to NOT_DISTRIBUTED with a reason."
    )
    orphan_modules = (
        _source_modules() - _distributed_modules() - NOT_DISTRIBUTED - NOT_DISTRIBUTED_MODULES
    )
    assert not orphan_modules, (
        f"{sorted(orphan_modules)} are absent from [tool.setuptools] py-modules, so they are "
        f"missing from an installed build."
    )
