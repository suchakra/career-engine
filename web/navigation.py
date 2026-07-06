"""Sidebar navigation view-model + injectable renderer (Phase 4A).

Repurposes the near-empty Streamlit left panel into a persistent navigation
sidebar. Same two-layer, UI-logic-only pattern as :mod:`web.dashboard`:

- :func:`build_sidebar_view` — a PURE map from the active view + the user's
  workspace to a :class:`SidebarView` (nav items + a compact applications list),
  testable without a Streamlit runtime.
- :func:`render_sidebar` — takes the view plus an injected ``st``-like module and
  emits the sidebar widgets. The caller wraps this in ``with st.sidebar:``.

Routing contract: nav selections only ever set ``st.session_state["view"]`` — they
never clear grill/tailor session state, so switching views does not lose an
in-progress grill. The active view's button is disabled (selecting it is a no-op).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from schema import UserWorkspace

# Ordered (view_key, label) pairs. The keys match the routing keys read in
# web/streamlit_app.py; "portfolio" is added here (its view lands in 4B).
NAV_ITEMS: tuple[tuple[str, str], ...] = (
    ("dashboard", "Dashboard"),
    ("portfolio", "Portfolio"),
    ("grill", "Grill"),
    ("jobs", "Jobs"),
    ("tailor", "Tailor"),
)
_NAV_KEYS = frozenset(key for key, _ in NAV_ITEMS)
_DEFAULT_VIEW = "dashboard"

_APPS_EMPTY_TEXT = "No tracked applications yet."


@dataclass(frozen=True)
class NavItem:
    """One navigation entry (display-ready, no Streamlit types)."""

    key: str
    label: str
    is_active: bool


@dataclass(frozen=True)
class SidebarView:
    """Display-ready sidebar state (fully testable without Streamlit)."""

    nav_items: list[NavItem]
    active_view: str
    applications: list[str] = field(default_factory=list)
    applications_empty_text: str = _APPS_EMPTY_TEXT


def _application_line(company: str, job_title: str, status: str) -> str:
    """One compact 'Company — Title · status' line (dashes for missing parts)."""
    return f"{company or '—'} — {job_title or '—'} · {status}"


def build_sidebar_view(workspace: UserWorkspace, *, active_view: str) -> SidebarView:
    """Build the sidebar view-model from the active view + workspace (pure).

    Args:
        workspace: The user's portfolio workspace (applications live here).
        active_view: The current ``st.session_state["view"]`` value; an unknown
            value falls back to the Dashboard so exactly one item is ever active.

    Returns:
        A :class:`SidebarView` ready to render.
    """
    active = active_view if active_view in _NAV_KEYS else _DEFAULT_VIEW
    nav_items = [NavItem(key=key, label=label, is_active=key == active) for key, label in NAV_ITEMS]
    applications = [
        _application_line(app.company, app.job_title, str(app.status.value))
        for app in workspace.applications
    ]
    return SidebarView(nav_items=nav_items, active_view=active, applications=applications)


def render_sidebar(view: SidebarView, *, st: Any) -> None:
    """Render the sidebar via an injected ``st``-like module.

    Emits one button per nav item (the active one disabled) and a compact
    applications list. Buttons only set the view key — never clear other session
    state — so an in-progress grill survives navigation.

    Args:
        view: The view-model from :func:`build_sidebar_view`.
        st: A Streamlit-like module (real ``streamlit`` in the app; a fake in tests).
    """
    st.caption("Navigate")
    for item in view.nav_items:
        st.button(
            item.label,
            key=f"nav_{item.key}",
            disabled=item.is_active,
            use_container_width=True,
            on_click=lambda k=item.key: st.session_state.__setitem__("view", k),
        )

    st.subheader("Applications")
    if view.applications:
        for line in view.applications:
            st.write(f"• {line}")
    else:
        st.write(view.applications_empty_text)


__all__ = ["NAV_ITEMS", "NavItem", "SidebarView", "build_sidebar_view", "render_sidebar"]
