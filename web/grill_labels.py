"""Streamlit-free "currently grilling" label helpers (shared by API + web grill).

These pure helpers derive the human label for the experience the grill is (or the
next turn will be) working on, from a :class:`~schema.CareerEngineState`. They were
extracted verbatim from ``web/grill_ui.py`` so the FastAPI transport layer can reuse
the SAME implementation without importing ``streamlit`` (BUG-2: one label impl, not
two). ``web/grill_ui.py`` now re-imports them from here.
"""

from __future__ import annotations

from schema import CareerEngineState, Entry

__all__ = ["_effective_frontier_label", "_entry_label", "_frontier_label"]


def _entry_label(entry: Entry | None) -> str:
    """Human 'Title · Org' label for an entry (title-only if no org); '' if None."""
    if entry is None:
        return ""
    parts = [entry.title or "this experience"]
    if entry.org:
        parts.append(entry.org)
    return " · ".join(parts)


def _frontier_label(state: CareerEngineState) -> str:
    """Human label for the experience currently pinned by grill_frontier, or ''."""
    fid = state.grill_frontier
    if not fid:
        return ""
    entry = next((e for e in state.work_timeline if str(e.entry_id) == fid), None)
    return _entry_label(entry)


def _effective_frontier_label(state: CareerEngineState) -> str:
    """Label for the experience being grilled — or the one the NEXT turn will grill.

    Equals :func:`_frontier_label` when ``grill_frontier`` is set and points at an
    entry still in the timeline. When the frontier is BLANK, fall back to the entry
    the grill node will auto-pick (:func:`workflows.nodes._get_frontier_entry`).

    Why (BUG-2): on resume, :func:`_migrate_education_on_resume` blanks
    ``grill_frontier`` when the pinned entry is no longer grillable (e.g. it was
    finished before the user left). The grill node re-pins the next entry on the
    NEXT turn, so reading ``grill_frontier`` alone left the "Currently grilling"
    banner empty on the FIRST question after coming back, then reappearing later.
    Deriving from the same selection the graph uses keeps the banner correct from
    the first question.
    """
    label = _frontier_label(state)
    if label:
        return label
    # Local import: web/ modules import from workflows.nodes inside functions to keep
    # the UI import path lightweight (matches _migrate_education_on_resume below).
    from workflows.nodes import _get_frontier_entry

    return _entry_label(_get_frontier_entry(state))
