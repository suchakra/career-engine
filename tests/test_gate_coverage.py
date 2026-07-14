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

import re
import tomllib
from pathlib import Path
from typing import Any

from setuptools import find_packages

REPO_ROOT = Path(__file__).resolve().parents[1]

# Source roots deliberately left out of the gate. Empty on purpose: an exemption must show
# up as a visible diff with a reason, never as a silent skip.
ALLOWED_UNGATED: frozenset[str] = frozenset()

# Gated by ruff/mypy, but not shipped in an installed build.
NOT_DISTRIBUTED: frozenset[str] = frozenset({"tests"})


def _source_dirs() -> set[str]:
    """Every top-level directory holding Python source.

    Presence of a ``.py`` file, not of an ``__init__.py`` — see the module docstring.
    """
    return {
        path.name
        for path in REPO_ROOT.iterdir()
        if path.is_dir() and not path.name.startswith(".") and any(path.glob("*.py"))
    }


def _source_modules() -> set[str]:
    """Every top-level Python module (``config.py``, ``schema.py``, ``main.py``)."""
    return {path.stem for path in REPO_ROOT.glob("*.py")}


def _src_dirs() -> set[str]:
    """The SRC_DIRS list that ``make lint`` and ``make typecheck`` hand to ruff and mypy."""
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    match = re.search(r"^SRC_DIRS\s*[:?+]?=\s*(.+)$", makefile, re.MULTILINE)
    assert match is not None, "No SRC_DIRS assignment in the Makefile — was it renamed?"
    return {entry.rstrip("/").removesuffix(".py") for entry in match.group(1).split()}


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
    found = find_packages(
        where=str(REPO_ROOT),
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
    orphan_modules = _source_modules() - _distributed_modules() - NOT_DISTRIBUTED
    assert not orphan_modules, (
        f"{sorted(orphan_modules)} are absent from [tool.setuptools] py-modules, so they are "
        f"missing from an installed build."
    )
