"""Extension seam for a private premium layer (open-core, ARCHITECTURE §17 / AD-17.2).

The core FastAPI app auto-mounts routers contributed by installed **plugin packages**,
discovered via the ``careerengine.plugins`` entry-point group. Dependency direction is
one-way: the core NEVER imports a plugin; a plugin imports the core and registers itself.

The core ships **zero** plugins — this is the seam a separate private package plugs into
in a commercial deploy. The same image can run with a plugin installed but disabled via
the ``CE_DISABLED_PLUGINS`` denylist, so OSS/demo and commercial deploys share one build.
"""

from __future__ import annotations

import logging
import os
from importlib.metadata import entry_points
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

_PLUGIN_GROUP = "careerengine.plugins"
_log = logging.getLogger("career_engine.api")


def _disabled_names() -> set[str]:
    """Names in the ``CE_DISABLED_PLUGINS`` comma-separated denylist (may be empty)."""
    raw = os.environ.get("CE_DISABLED_PLUGINS", "")
    return {name.strip() for name in raw.split(",") if name.strip()}


def load_plugins(app: FastAPI) -> list[str]:
    """Discover + register installed plugins onto ``app``; return the names that loaded.

    Each entry point in the ``careerengine.plugins`` group resolves to a
    ``register(app: FastAPI) -> None`` callable that mounts its own routers/deps. A
    plugin listed in ``CE_DISABLED_PLUGINS`` is skipped. A plugin that raises during
    load or registration is skipped too — a broken add-on must never take down the core
    (the one-way dependency rule cuts both ways: the core stays up regardless of the
    private layer).
    """
    disabled = _disabled_names()
    loaded: list[str] = []
    for entry in entry_points(group=_PLUGIN_GROUP):
        if entry.name in disabled:
            continue
        try:
            register = entry.load()
            register(app)
        except Exception as exc:  # isolate a broken plugin from the core
            # Preserve the "a broken plugin can't crash the core" guarantee, but log it
            # so "plugin present but broken" is distinguishable from "no plugins".
            _log.warning(
                "Plugin %r failed to load/register (%s); skipping.",
                entry.name,
                type(exc).__name__,
            )
            continue
        loaded.append(entry.name)
    return loaded
