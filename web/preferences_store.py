"""Persisted job-discovery preferences (Phase 7A).

The web Jobs view needs a saved evaluation rubric (target roles / nice-to-haves /
dealbreakers) so it isn't re-entered each visit. This persists it as a
:class:`schema.SessionPreferences` on the user's :class:`schema.UserWorkspace`
(``discovery_preferences``, additive v2.8.0).

Pure + injectable over any store exposing sync ``load(user_id)`` /
``save(user_id, workspace)`` (the real
:class:`database.workspace_store.FirestoreWorkspaceStore` or a test double), so the
logic is unit-tested without GCP. Only user-provided rubric text is stored — never
a BYOK key or other secret. Mirrors :mod:`web.profile_store`.
"""

from __future__ import annotations

from schema import SessionPreferences
from web.application_store import WorkspaceStore


def load_discovery_preferences(store: WorkspaceStore, *, user_id: str) -> SessionPreferences:
    """Return the user's persisted discovery preferences (empty for a new user).

    Returns a defensive deep copy so a caller mutating the result can't write
    through to a store that returned a cached/shared workspace.
    """
    return store.load(user_id).discovery_preferences.model_copy(deep=True)


def save_discovery_preferences(
    store: WorkspaceStore, *, user_id: str, preferences: SessionPreferences
) -> None:
    """Persist the user's discovery preferences, preserving the rest of the workspace.

    Read-modify-write with copy-on-write (mirrors ``save_profile`` /
    ``save_tailored_application``): the loaded workspace is not mutated in place, and
    ``applications`` / ``pending_actions`` / ``profile`` are carried through unchanged.
    Same single-writer caveat applies (full-document ``set``).
    """
    workspace = store.load(user_id)
    updated = workspace.model_copy(update={"discovery_preferences": preferences})
    store.save(user_id, updated)


__all__ = ["load_discovery_preferences", "save_discovery_preferences"]
