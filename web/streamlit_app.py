"""Streamlit entrypoint for the CareerEngine web workspace (Phase 2A).

Run with: ``streamlit run web/streamlit_app.py`` (or ``career-engine web``).

This is a THIN shell: it resolves "today" at the boundary, obtains the user's
session + workspace state, and delegates all rendering to
:func:`web.dashboard.render_dashboard`. No workflow/business logic here.

Wiring note (Phase 2 follow-ups): authenticated user resolution (2B) and a
Firestore-backed UserWorkspace repository are not yet wired, so this currently
renders an empty workspace. The view-model + renderer are complete and tested;
only the load/auth seam remains.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from schema import CareerEngineState, UserWorkspace
from web.dashboard import build_dashboard_view, render_dashboard


def main() -> None:
    """Build the dashboard view-model from current state and render it."""
    today = date.today().isoformat()  # the one wall-clock read, at the boundary

    # TODO(2B + workspace repo): replace with the authenticated user's loaded
    # discovery session state + UserWorkspace. Until then: empty workspace.
    state = CareerEngineState(reference_date=today)
    workspace = UserWorkspace()

    view = build_dashboard_view(state, workspace, today=today)
    render_dashboard(view, st=st)


main()
