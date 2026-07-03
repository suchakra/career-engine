"""Streamlit entrypoint for the CareerEngine web workspace (Phase 2A/2B).

Run with: ``streamlit run web/streamlit_app.py`` (or ``career-engine web``).

Auth: **Streamlit native OIDC** (``st.login`` / ``st.user`` / ``st.logout``) — a real
Google / Identity Platform sign-in. Configure the ``[auth]`` section in
``.streamlit/secrets.toml`` (see ``.streamlit/secrets.toml.example``); Streamlit
verifies the OIDC token and exposes the claims on ``st.user``. The stable subject
(``st.user["sub"]``) is the ``user_id`` namespace key for the workspace + discovery
session — never an API key (ARCHITECTURE §5). BYOK keys stay in Secret Manager.

Thin shell: authenticate, load the user's workspace + latest discovery state, and
delegate rendering to :func:`web.dashboard.render_dashboard`. No workflow logic here.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from schema import CareerEngineState, UserWorkspace
from web.dashboard import build_dashboard_view, render_dashboard


def _current_user_id() -> str:
    """Return the stable OIDC subject as the user_id (falls back to email)."""
    sub = st.user.get("sub") or st.user.get("email")
    return str(sub) if sub else ""


def _load_workspace(user_id: str) -> UserWorkspace:
    """Best-effort load of the user's workspace; empty on any backend failure."""
    from database.workspace_store import FirestoreWorkspaceStore

    try:
        return FirestoreWorkspaceStore().load(user_id)
    except Exception:
        return UserWorkspace()


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


def _render_signin() -> None:
    """Render the signed-out landing page with a real sign-in button."""
    st.title("CareerEngine")
    st.write(
        "Turn a stale, vague career history into **quantified, ATS-ready STAR résumés** "
        "through an agentic “grill” loop — privacy-first, cost-efficient, reproducible."
    )
    st.info("Sign in to view your workspace.")
    st.button("Sign in with Google", type="primary", on_click=st.login)


def main() -> None:
    """Authenticate (native OIDC), load state, and render the dashboard."""
    from workflows.observability import configure_logging

    configure_logging()

    if not st.user.is_logged_in:
        _render_signin()
        return

    user_id = _current_user_id()
    if not user_id:
        st.error("Signed in, but your profile has no stable identifier — cannot continue.")
        st.button("Sign out", on_click=st.logout)
        return

    today = date.today().isoformat()  # the one wall-clock read, at the boundary
    with st.sidebar:
        st.caption(f"Signed in as {st.user.get('email') or user_id}")
        st.button("Sign out", on_click=st.logout)

    workspace = _load_workspace(user_id)
    state = _load_discovery_state(user_id=user_id, today=today)
    view = build_dashboard_view(state, workspace, today=today)
    render_dashboard(view, st=st)


main()
