"""The quality gate must cover every Python package — including ones added later.

CLEAN-2: ``api/`` was missing from the Makefile's ``SRC_DIRS``, so ruff never ran over the
FastAPI layer — every route and every wire DTO, i.e. the files where the contract lives.
The gate had a hole exactly where the contract lives.

Two lists decide a package's fate, both hand-maintained, and both had forgotten ``api``:
``SRC_DIRS`` (what ruff and mypy check) and ``[tool.setuptools.packages.find].include``
(what an installed build contains). A hand-maintained list drifts in silence; these tests
make it drift loudly instead.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Packages deliberately left out of the gate. Empty on purpose: an exemption must show up
# as a visible diff with a reason, never as a silent skip.
ALLOWED_UNGATED: frozenset[str] = frozenset()

# Checked by the gate, but not shipped in an installed build.
NOT_DISTRIBUTED: frozenset[str] = frozenset({"tests"})


def _source_packages() -> set[str]:
    """Every top-level importable package in the repo (a directory with an __init__.py)."""
    return {
        path.name
        for path in REPO_ROOT.iterdir()
        if path.is_dir() and (path / "__init__.py").is_file()
    }


def _src_dirs() -> set[str]:
    """The SRC_DIRS list that ``make lint`` and ``make typecheck`` hand to ruff and mypy."""
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    match = re.search(r"^SRC_DIRS\s*[:?]?=\s*(.+)$", makefile, re.MULTILINE)
    assert match is not None, "No SRC_DIRS assignment in the Makefile — was it renamed?"
    return {entry.rstrip("/") for entry in match.group(1).split()}


def _distributed_packages() -> set[str]:
    """The package list an installed build is built from."""
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    include: list[str] = pyproject["tool"]["setuptools"]["packages"]["find"]["include"]
    return {entry.rstrip("*") for entry in include}


def test_the_parsers_are_not_vacuous() -> None:
    """Guard the guard: a reformatted Makefile must not quietly yield an empty list.

    Without this, a rename or a line-continuation makes the regex match nothing, every
    other assertion below passes over an empty set, and the gate hole reopens undetected.
    """
    assert "tests" in _src_dirs(), "SRC_DIRS parsed to something wrong — the regex is stale"
    assert "web" in _distributed_packages(), "pyproject's package list parsed to something wrong"
    assert _source_packages() >= {"api", "web"}, "package discovery is not finding the repo"


def test_every_package_is_linted_and_typechecked() -> None:
    missing = _source_packages() - _src_dirs() - ALLOWED_UNGATED
    assert not missing, (
        f"{sorted(missing)} are absent from the Makefile's SRC_DIRS, so `make check` never "
        f"lints or typechecks them. Add them to SRC_DIRS — or, if that is deliberate, to "
        f"ALLOWED_UNGATED with a reason."
    )


def test_every_package_is_distributed() -> None:
    missing = _source_packages() - _distributed_packages() - NOT_DISTRIBUTED
    assert not missing, (
        f"{sorted(missing)} are absent from [tool.setuptools.packages.find].include in "
        f"pyproject.toml, so they are missing from an installed build."
    )
