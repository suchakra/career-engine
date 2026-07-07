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

from schema import CareerEngineState, SessionPreferences
from web.application_store import WorkspaceStore


def derive_initial_roles(state: CareerEngineState) -> list[str]:
    """Return the top-3 most recent Entry titles as initial ``target_roles`` hints.

    Used to seed the Jobs preference form for a user who has never saved a rubric,
    so the very first discovery run reflects their own recent experience instead of
    the operator's demo defaults. Entries with empty titles are dropped first, then
    the remainder is ordered by ``end_date`` descending (a blank ``end_date`` means
    "present" and sorts newest) and the top three titles are returned — so blank
    recent titles never crowd out valid older ones. Pure — no I/O.
    """
    titled = sorted(
        (e for e in state.work_timeline if e.title),
        key=lambda e: (e.end_date or "9999"),
        reverse=True,
    )
    return [e.title for e in titled[:3]]


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


__all__ = ["derive_initial_roles", "load_discovery_preferences", "save_discovery_preferences"]
