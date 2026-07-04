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
from typing import Any

import streamlit as st

from schema import CareerEngineState, UserWorkspace
from web.dashboard import build_dashboard_view, render_dashboard


def _current_user_id() -> str:
    """Return the stable OIDC subject as the user_id.

    Uses ONLY the ``sub`` claim — never email. `user_id` keys Secret Manager
    (`ce-key-{user_id}`) + Firestore docs; email contains `@` (invalid in secret
    ids) and isn't the stable subject. Missing `sub` → "" (caller errors out).
    """
    sub = st.user.get("sub")
    return str(sub) if sub else ""


def _load_workspace(user_id: str) -> UserWorkspace:
    """Load the user's workspace. Empty for a new user; a schema-version mismatch
    is surfaced (not silently shown as empty); a transient backend error warns."""
    from database.firestore_session import ContractVersionError
    from database.workspace_store import FirestoreWorkspaceStore

    try:
        return FirestoreWorkspaceStore().load(user_id)
    except ContractVersionError:
        raise  # a schema mismatch must not masquerade as an empty (lost) workspace
    except Exception:
        st.warning("Couldn't reach your saved workspace just now — showing an empty view.")
        return UserWorkspace()


@st.cache_resource(show_spinner=False)
def _build_session_service() -> Any:
    """Construct a FirestoreSessionService (its async Firestore client is expensive).

    Cached across reruns/sessions so we don't churn a new client per interaction.
    The service is identity-agnostic — app_name/user_id are passed per call — so a
    shared instance is safe. A construction failure raises (not cached by
    cache_resource), so a transient outage isn't pinned forever.
    """
    from database.firestore_session import FirestoreSessionService

    return FirestoreSessionService()


def _session_service() -> Any | None:
    """Return the cached FirestoreSessionService, or None if it can't be built."""
    try:
        return _build_session_service()
    except Exception:
        return None


def _load_discovery_state(*, user_id: str, today: str) -> CareerEngineState:
    """Resolve the user's latest discovery state, or an empty state on any failure."""
    from config import get_settings
    from web.session_loader import try_load_latest_discovery_state

    service = _session_service()
    if service is None:
        return CareerEngineState(reference_date=today)
    return try_load_latest_discovery_state(
        service,
        app_name=get_settings().app_name,
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

    # Load the workspace once — the sidebar (applications list) and the dashboard
    # both read it, so we avoid a double Firestore round-trip per rerun.
    workspace = _load_workspace(user_id)
    view_name = st.session_state.get("view", "dashboard")

    with st.sidebar:
        from web.navigation import build_sidebar_view, render_sidebar

        st.caption(f"Signed in as {st.user.get('email') or user_id}")
        st.button("Sign out", on_click=st.logout)
        st.divider()
        render_sidebar(build_sidebar_view(workspace, active_view=view_name), st=st)

    # View routing — sidebar + dashboard buttons set st.session_state["view"].
    if view_name == "grill":
        from web.grill_ui import render_grill

        render_grill(user_id=user_id)
        return
    if view_name == "tailor":
        _render_tailor(user_id=user_id)
        return
    if view_name == "portfolio":
        _render_portfolio(user_id=user_id, today=today)
        return

    state = _load_discovery_state(user_id=user_id, today=today)
    view = build_dashboard_view(state, workspace, today=today)
    render_dashboard(view, st=st)


def _jump_grill_to_entry(*, user_id: str, entry_id: str) -> None:
    """Route to the Grill view and signal it to grill THIS experience (4C).

    The grill view (``_apply_pending_jump``) pins the frontier and runs a turn so
    it actually asks about this entry — a live in-browser session would otherwise
    keep showing the previous question.
    """
    st.session_state["grill_jump_to"] = entry_id
    st.session_state["view"] = "grill"


def _render_add_experience_form(*, user_id: str, today: str) -> None:
    """Form to add a remembered experience/project into the timeline (4D)."""
    from config import get_settings
    from schema import ExperienceType
    from web.portfolio_store import add_manual_entry

    type_values = [t.value for t in ExperienceType]
    with st.expander("Add an experience or project"):
        st.caption(
            "Spent years somewhere with more projects than your résumé shows? Add one "
            "here and grill it into a quantified achievement."
        )
        with st.form("add_experience", clear_on_submit=True):
            title = st.text_input("Title", placeholder="e.g. Re-architected the billing pipeline")
            org = st.text_input("Organisation", placeholder="e.g. same employer as the role")
            experience_type = st.selectbox(
                "Type", type_values, index=type_values.index(ExperienceType.PROJECT.value)
            )
            start_date = st.text_input("Start (YYYY or YYYY-MM)", placeholder="2019")
            end_date = st.text_input("End (blank = present)", placeholder="2021")
            notes = st.text_area("Notes / existing bullets (one per line)")
            submitted = st.form_submit_button("Add to my portfolio")

        if submitted:
            if not title.strip():
                st.warning("Give the experience a title so it can be grilled.")
                return
            service = _session_service()
            if service is None:
                st.error("Couldn't reach your workspace to save this — please try again.")
                return
            try:
                add_manual_entry(
                    service,
                    app_name=get_settings().app_name,
                    user_id=user_id,
                    reference_date=today,
                    title=title,
                    org=org,
                    experience_type=ExperienceType(experience_type),
                    start_date=start_date,
                    end_date=end_date,
                    bullets=notes.splitlines(),
                )
            except Exception:
                st.error("Couldn't save that just now — please try again.")
                return
            st.success(f"Added “{title.strip()}”. It's in your portfolio and ready to grill.")
            st.rerun()


def _render_portfolio(*, user_id: str, today: str) -> None:
    """Read-only Portfolio view + steer/add controls (4B/4C/4D)."""
    from web.portfolio import build_portfolio_view, render_portfolio

    state = _load_discovery_state(user_id=user_id, today=today)

    def _grill_entry(entry_id: str) -> None:
        _jump_grill_to_entry(user_id=user_id, entry_id=entry_id)

    render_portfolio(build_portfolio_view(state), st=st, on_grill_entry=_grill_entry)
    _render_add_experience_form(user_id=user_id, today=today)


def _render_tailor(*, user_id: str) -> None:
    """Placeholder tailor view — web tailor is a follow-up; the CLI works today."""
    if st.button("← Dashboard"):
        st.session_state["view"] = "dashboard"
        st.rerun()
    st.title("Tailor a résumé")
    st.info(
        "Tailoring a completed résumé to a job description is available via the CLI today "
        "(`career-engine tailor <session-id> <jd>`); the in-app tailor flow is a follow-up. "
        "Finish a **Grill Me** session first to build your master résumé."
    )


main()
