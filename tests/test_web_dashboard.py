"""Tests for the web dashboard view-model + renderer (Phase 2A).

The renderer takes an injected fake ``st``, so the UX is tested without the
Streamlit runtime. Covers: boots/renders, nudge shown/hidden, tailor entry
point never gated, and pending-action rendering.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from schema import (
    Application,
    CareerEngineState,
    Entry,
    EntryStatus,
    ExperienceType,
    PendingAction,
    UserWorkspace,
)
from web.dashboard import DashboardView, build_dashboard_view, render_dashboard

REF_DATE = "2026-06-30"


class FakeSt:
    """Records Streamlit calls so tests can assert what was rendered."""

    def __init__(self) -> None:
        self.titles: list[str] = []
        self.captions: list[str] = []
        self.warnings: list[str] = []
        self.subheaders: list[str] = []
        self.writes: list[Any] = []
        self.buttons: list[str] = []
        # Captures full kwargs per button (label included) for on_click routing tests.
        self.button_calls: list[dict[str, Any]] = []
        # Minimal session_state so on_click lambdas can write to it.
        self.session_state: dict[str, Any] = {}

    def title(self, body: str) -> None:
        self.titles.append(body)

    def caption(self, body: str) -> None:
        self.captions.append(body)

    def warning(self, body: str) -> None:
        self.warnings.append(body)

    def subheader(self, body: str) -> None:
        self.subheaders.append(body)

    def write(self, body: Any) -> None:
        self.writes.append(body)

    def button(self, label: str, **kwargs: Any) -> None:
        self.buttons.append(label)
        self.button_calls.append({"label": label, **kwargs})


def _incomplete_state() -> CareerEngineState:
    """Recent window with a pending entry → nudge should show."""
    return CareerEngineState(
        reference_date=REF_DATE,
        work_timeline=[
            Entry(
                type=ExperienceType.FULL_TIME,
                title="Current",
                start_date="2022",
                end_date="",
                status=EntryStatus.GRILLED,
            ),
            Entry(
                type=ExperienceType.FULL_TIME,
                title="Recent",
                start_date="2023",
                end_date="2024",
                status=EntryStatus.NEEDS_QUANTIFYING,
            ),
        ],
    )


def _complete_state() -> CareerEngineState:
    """Fully-grilled recent window → nudge should hide."""
    return CareerEngineState(
        reference_date=REF_DATE,
        work_timeline=[
            Entry(
                type=ExperienceType.FULL_TIME,
                title="Current",
                start_date="2022",
                end_date="",
                status=EntryStatus.GRILLED,
            ),
        ],
    )


class TestBuildDashboardView:
    """build_dashboard_view maps state + workspace into a display-ready view."""

    def test_incomplete_window_shows_nudge(self, tmp_path: Path) -> None:
        """An incomplete recent window flags the nudge."""
        view = build_dashboard_view(
            _incomplete_state(), UserWorkspace(), today=REF_DATE, prefs_path=tmp_path / "p.json"
        )
        assert view.show_nudge is True
        assert "50% documented" in view.progress_meter
        assert view.can_tailor is True  # never gated

    def test_complete_window_hides_nudge(self, tmp_path: Path) -> None:
        """A complete recent window hides the nudge."""
        view = build_dashboard_view(
            _complete_state(), UserWorkspace(), today=REF_DATE, prefs_path=tmp_path / "p.json"
        )
        assert view.show_nudge is False

    def test_pending_actions_and_counts_mapped(self, tmp_path: Path) -> None:
        """Pending actions and application count come through to the view."""
        ws = UserWorkspace(
            applications=[Application(company="Acme"), Application(company="Globex")],
            pending_actions=[PendingAction(application_id="a1", reason="Follow up with Acme.")],
        )
        view = build_dashboard_view(
            _complete_state(), ws, today=REF_DATE, prefs_path=tmp_path / "p.json"
        )
        assert view.application_count == 2
        assert view.pending_actions == ["Follow up with Acme."]


class TestRenderDashboard:
    """render_dashboard maps the view to widgets via an injected fake st."""

    def _view(self, *, show_nudge: bool, pending: list[str]) -> DashboardView:
        return DashboardView(
            progress_meter="Recent 5-yr window: 50% documented · portfolio depth: 4 yrs",
            show_nudge=show_nudge,
            nudge_message="fill in the rest of your recent history",
            pending_actions=pending,
            application_count=len(pending),
        )

    def test_boots_and_renders_title(self) -> None:
        """The dashboard renders without error and shows the title."""
        st = FakeSt()
        render_dashboard(self._view(show_nudge=False, pending=[]), st=st)
        assert "CareerEngine" in st.titles

    def test_nudge_rendered_when_shown(self) -> None:
        """show_nudge=True emits a warning with the nudge message."""
        st = FakeSt()
        render_dashboard(self._view(show_nudge=True, pending=[]), st=st)
        assert any("recent history" in w for w in st.warnings)

    def test_nudge_not_rendered_when_hidden(self) -> None:
        """show_nudge=False emits no warning."""
        st = FakeSt()
        render_dashboard(self._view(show_nudge=False, pending=[]), st=st)
        assert st.warnings == []

    def test_tailor_entry_point_always_rendered_even_with_nudge(self) -> None:
        """Tailoring is never gated — the entry point shows even with the nudge."""
        st = FakeSt()
        render_dashboard(self._view(show_nudge=True, pending=[]), st=st)
        assert "Tailor a resume" in st.buttons

    def test_grill_entry_point_always_rendered_even_with_nudge(self) -> None:
        """Grilling is never gated either — the entry point shows even with the nudge."""
        st = FakeSt()
        render_dashboard(self._view(show_nudge=True, pending=[]), st=st)
        assert "Start / continue grilling" in st.buttons

    def test_pending_action_rendered(self) -> None:
        """A pending-action item is written to the dashboard."""
        st = FakeSt()
        render_dashboard(self._view(show_nudge=False, pending=["Follow up with Acme."]), st=st)
        assert any("Follow up with Acme." in str(w) for w in st.writes)

    def test_find_jobs_button_present(self) -> None:
        """'Find jobs' is always rendered alongside Grill and Tailor (never gated)."""
        st = FakeSt()
        render_dashboard(self._view(show_nudge=False, pending=[]), st=st)
        assert "Find jobs" in st.buttons

    def test_find_jobs_on_click_routes_to_jobs_view(self) -> None:
        """The 'Find jobs' button's on_click callback sets view='jobs' in session_state."""
        st = FakeSt()
        render_dashboard(self._view(show_nudge=False, pending=[]), st=st)
        call = next((c for c in st.button_calls if c["label"] == "Find jobs"), None)
        assert call is not None, "'Find jobs' button not found in button_calls"
        on_click = call.get("on_click")
        assert callable(on_click), "'Find jobs' button has no on_click"
        on_click()
        assert st.session_state.get("view") == "jobs"
