"""Streamlit entrypoint for the CareerEngine web workspace (Phase 2A/2B).

Run with: ``streamlit run web/streamlit_app.py`` (or ``career-engine web``).

Thin shell: resolve "today" at the boundary, authenticate the caller (2B), load
their workspace (real WorkspaceStore), and delegate rendering to
:func:`web.dashboard.render_dashboard`. No workflow/business logic here.

Wiring note: the frontend obtains an Identity Platform ID token and passes it in
(here read from ``st.query_params['id_token']`` or ``st.session_state``). Loading
the user's *discovery session* state (for the progress meter) is a thin
follow-up; until then the meter reflects an empty session while the
workspace/pending-actions surface is live per authenticated user.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from auth.firebase_auth import FirebaseAuthProvider
from database.workspace_store import FirestoreWorkspaceStore
from schema import CareerEngineState
from web.bootstrap import try_bootstrap_web_session
from web.dashboard import build_dashboard_view, render_dashboard


def _read_id_token() -> str | None:
    """Read the Identity Platform ID token from query params or session state."""
    token = st.query_params.get("id_token") or st.session_state.get("id_token")
    # Only accept a non-empty string; a non-str session_state value is ignored.
    return token if isinstance(token, str) and token else None


def main() -> None:
    """Authenticate, load the workspace, and render the dashboard (or a sign-in prompt)."""
    from workflows.observability import configure_logging

    configure_logging()
    today = date.today().isoformat()  # the one wall-clock read, at the boundary

    session = try_bootstrap_web_session(
        id_token=_read_id_token(),
        auth_provider=FirebaseAuthProvider(),
        workspace_store=FirestoreWorkspaceStore(),
    )

    if session is None:
        st.title("CareerEngine")
        st.info("Please sign in to view your workspace.")
        return

    # Load this user's latest discovery-session state for the progress meter.
    # Best-effort: an empty state (no progress) is rendered if the backend is
    # unreachable or the user has no session yet — never crash the dashboard.
    state = _load_discovery_state(user_id=session.user_id, today=today)
    view = build_dashboard_view(state, session.workspace, today=today)
    render_dashboard(view, st=st)


def _load_discovery_state(*, user_id: str, today: str) -> CareerEngineState:
    """Resolve the user's latest discovery state, or an empty state on any failure."""
    from config import get_settings
    from database.firestore_session import FirestoreSessionService
    from web.session_loader import try_load_latest_discovery_state

    settings = get_settings()
    try:
        session_service = FirestoreSessionService()
    except Exception:
        return CareerEngineState(reference_date=today)
    return try_load_latest_discovery_state(
        session_service,
        app_name=settings.app_name,
        user_id=user_id,
        reference_date=today,
    )


main()
