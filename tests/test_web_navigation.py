"""Tests for the sidebar navigation view-model + renderer (Phase 4A).

The renderer takes an injected fake ``st``, so navigation is tested without a
Streamlit runtime. Covers: nav items + active resolution, application-list
mapping + empty state, and the routing invariant that nav only sets the view key
(never clobbers in-progress grill/tailor session state).
"""

from __future__ import annotations

from typing import Any

from schema import Application, ApplicationStatus, UserWorkspace
from web.navigation import (
    NAV_ITEMS,
    SidebarView,
    build_sidebar_view,
    render_sidebar,
)


class FakeSt:
    """Records sidebar calls (and holds a session_state) for assertions."""

    def __init__(self) -> None:
        self.captions: list[str] = []
        self.subheaders: list[str] = []
        self.writes: list[Any] = []
        self.buttons: list[tuple[str, dict[str, Any]]] = []
        self.session_state: dict[str, Any] = {}

    def caption(self, body: str) -> None:
        self.captions.append(body)

    def subheader(self, body: str) -> None:
        self.subheaders.append(body)

    def write(self, body: Any) -> None:
        self.writes.append(body)

    def button(self, label: str, **kwargs: Any) -> None:
        self.buttons.append((label, kwargs))


class TestBuildSidebarView:
    """build_sidebar_view maps active view + workspace into a display-ready view."""

    def test_nav_items_cover_all_views_with_one_active(self) -> None:
        """Every nav view is present and exactly the active one is flagged."""
        view = build_sidebar_view(UserWorkspace(), active_view="grill")
        assert [item.key for item in view.nav_items] == [key for key, _ in NAV_ITEMS]
        active = [item.key for item in view.nav_items if item.is_active]
        assert active == ["grill"]
        assert view.active_view == "grill"

    def test_unknown_view_falls_back_to_dashboard(self) -> None:
        """An unknown/empty active view resolves to Dashboard (exactly one active)."""
        view = build_sidebar_view(UserWorkspace(), active_view="nonsense")
        active = [item.key for item in view.nav_items if item.is_active]
        assert active == ["dashboard"]
        assert view.active_view == "dashboard"

    def test_applications_mapped(self) -> None:
        """Applications render as compact company/title/status lines."""
        ws = UserWorkspace(
            applications=[
                Application(
                    company="Acme", job_title="SRE", status=ApplicationStatus.INTERVIEW
                ),
                Application(company="Globex", job_title="Eng"),
            ]
        )
        view = build_sidebar_view(ws, active_view="dashboard")
        assert view.applications[0] == "Acme — SRE · interview"
        assert view.applications[1] == "Globex — Eng · applied"

    def test_no_applications_yields_empty_list(self) -> None:
        """A workspace with no applications yields an empty list (empty-state text used)."""
        view = build_sidebar_view(UserWorkspace(), active_view="dashboard")
        assert view.applications == []
        assert view.applications_empty_text


class TestRenderSidebar:
    """render_sidebar maps the view to widgets via an injected fake st."""

    def test_active_item_button_is_disabled(self) -> None:
        """The active nav item's button is disabled (selecting it is a no-op)."""
        st = FakeSt()
        render_sidebar(build_sidebar_view(UserWorkspace(), active_view="portfolio"), st=st)
        disabled = {label: kw.get("disabled") for label, kw in st.buttons}
        assert disabled["Portfolio"] is True
        assert disabled["Dashboard"] is False

    def test_empty_state_text_rendered_when_no_applications(self) -> None:
        """The empty-state string shows when there are no applications."""
        st = FakeSt()
        view = build_sidebar_view(UserWorkspace(), active_view="dashboard")
        render_sidebar(view, st=st)
        assert any(view.applications_empty_text in str(w) for w in st.writes)

    def test_application_lines_rendered(self) -> None:
        """Application lines are written to the sidebar."""
        st = FakeSt()
        ws = UserWorkspace(applications=[Application(company="Acme", job_title="SRE")])
        render_sidebar(build_sidebar_view(ws, active_view="dashboard"), st=st)
        assert any("Acme — SRE" in str(w) for w in st.writes)

    def test_nav_click_sets_view_and_preserves_other_session_state(self) -> None:
        """Clicking a nav item sets only the view key — grill state is untouched."""
        st = FakeSt()
        st.session_state["grill_session_id"] = "sess-123"
        st.session_state["view"] = "dashboard"
        render_sidebar(build_sidebar_view(UserWorkspace(), active_view="dashboard"), st=st)

        on_click = {label: kw["on_click"] for label, kw in st.buttons}
        on_click["Grill"]()  # simulate the click

        assert st.session_state["view"] == "grill"
        assert st.session_state["grill_session_id"] == "sess-123"  # preserved


def test_sidebar_view_is_frozen() -> None:
    """SidebarView is an immutable value object (defensive, like DashboardView)."""
    view = build_sidebar_view(UserWorkspace(), active_view="dashboard")
    assert isinstance(view, SidebarView)
    import dataclasses

    import pytest

    with pytest.raises(dataclasses.FrozenInstanceError):
        view.active_view = "grill"  # type: ignore[misc]
