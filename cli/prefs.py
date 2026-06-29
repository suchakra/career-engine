"""Local CLI preferences — snooze state for the progressive-discovery nudge.

This is UI state, so it deliberately lives OUTSIDE ``CareerEngineState`` (the
contract forbids UI state on the session object).  It is a small per-machine
JSON file under the user config directory.

Determinism: callers inject "today" (read ``date.today()`` only at the CLI
boundary, never inside logic) so the snooze decision is testable.

NOTE (Phase 2): when the §8 cross-device dashboard/workspace doc lands, this
snooze migrates there so it follows the user across devices.  Until then it is
intentionally local-only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_SNOOZE_KEY = "snooze_until"


def default_prefs_path() -> Path:
    """Return the default preferences file path under the user config dir."""
    return Path.home() / ".config" / "career-engine" / "prefs.json"


def _resolve_path(path: Path | None) -> Path:
    """Return the explicit path or the default."""
    return path if path is not None else default_prefs_path()


def load_prefs(*, path: Path | None = None) -> dict[str, Any]:
    """Load the preferences dict, returning {} if missing or unreadable."""
    p = _resolve_path(path)
    try:
        data: object = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_prefs(prefs: dict[str, Any], *, path: Path | None = None) -> None:
    """Persist the preferences dict, creating parent directories as needed."""
    p = _resolve_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(prefs, indent=2), encoding="utf-8")


def get_snooze_until(*, path: Path | None = None) -> str:
    """Return the ISO date the nudge is snoozed until, or "" if not snoozed."""
    value = load_prefs(path=path).get(_SNOOZE_KEY, "")
    return value if isinstance(value, str) else ""


def set_snooze_until(snooze_until: str, *, path: Path | None = None) -> None:
    """Persist the snooze-until ISO date (the nudge stays quiet before it)."""
    prefs = load_prefs(path=path)
    prefs[_SNOOZE_KEY] = snooze_until
    save_prefs(prefs, path=path)


def is_snoozed(today: str, *, path: Path | None = None) -> bool:
    """Return True if the nudge is currently snoozed relative to ``today``.

    ISO ``YYYY-MM-DD`` strings compare lexicographically, so ``today <
    snooze_until`` is a correct date comparison.  Once ``today`` reaches or
    passes ``snooze_until``, the nudge is no longer suppressed.

    Args:
        today: The injected current date (ISO ``YYYY-MM-DD``).
        path: Optional override for the prefs file (tests pass a tmp path).

    Returns:
        True while the snooze window is still in the future.
    """
    snooze_until = get_snooze_until(path=path)
    return bool(snooze_until) and today < snooze_until
