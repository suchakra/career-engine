"""Persisted résumé-header identity (Phase 5 — persist Contact).

The Tailor needs a contact header (name/email/phone/location/links). Previously it
lived only in Streamlit ``session_state`` and was re-typed every session; this
persists it as a :class:`schema.UserProfile` on the user's
:class:`schema.UserWorkspace`, so the contact form pre-fills next time.

Pure + injectable over any store exposing sync ``load(user_id)`` /
``save(user_id, workspace)`` (the real
:class:`database.workspace_store.FirestoreWorkspaceStore` or a test double), so the
logic is unit-tested without GCP. Only self-provided contact details are stored —
never a BYOK key or other secret.
"""

from __future__ import annotations

from schema import UserProfile
from web.application_store import WorkspaceStore


def load_profile(store: WorkspaceStore, *, user_id: str) -> UserProfile:
    """Return the user's persisted profile (empty for a new user).

    Returns a defensive copy so a caller mutating the result can't accidentally
    write through to a store that returned a cached/shared workspace instance.
    """
    return store.load(user_id).profile.model_copy(deep=True)


def save_profile(store: WorkspaceStore, *, user_id: str, profile: UserProfile) -> None:
    """Persist the user's profile, preserving the rest of the workspace.

    Read-modify-write with copy-on-write (mirrors ``save_tailored_application``): the
    loaded workspace is not mutated in place, and ``applications`` / ``pending_actions``
    are carried through unchanged. Same single-writer caveat applies (full-document
    ``set`` — see :func:`web.application_store.save_tailored_application`).
    """
    workspace = store.load(user_id)
    updated = workspace.model_copy(update={"profile": profile})
    store.save(user_id, updated)


__all__ = ["load_profile", "save_profile"]
