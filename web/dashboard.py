"""Dashboard view-model + injectable renderer (Phase 2A).

Two layers, both UI-logic-only (no workflow/business logic):

- :func:`build_dashboard_view` — a PURE map from session + workspace state to a
  :class:`DashboardView` (strings/flags ready to display). Reuses the shared
  presentation helpers so CLI and web stay consistent.
- :func:`render_dashboard` — takes the view plus an injected ``st``-like module
  and emits widgets. Injecting ``st`` keeps it testable with a fake (no
  Streamlit runtime needed); ``web/streamlit_app.py`` passes the real
  ``streamlit``.

Core principle (carried from the CLI): discovery is a NUDGE, never a gate —
``can_tailor`` is always True; the tailor entry point is always rendered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from cli.app import discovery_nudge_message, render_progress_meter, should_show_nudge
from schema import CareerEngineState, UserWorkspace


@dataclass(frozen=True)
class DashboardView:
    """Display-ready dashboard state (no Streamlit types, fully testable)."""

    progress_meter: str
    show_nudge: bool
    nudge_message: str
    pending_actions: list[str]
    application_count: int
    can_tailor: bool = True  # discovery is a nudge, never a gate
    can_start_grill: bool = True
    pending_actions_detail: list[dict[str, str]] = field(default_factory=list)


def build_dashboard_view(
    state: CareerEngineState,
    workspace: UserWorkspace,
    *,
    today: str,
    prefs_path: Any | None = None,
) -> DashboardView:
    """Build the dashboard view-model from session + workspace state (pure).

    Args:
        state: The user's current discovery session state.
        workspace: The user's portfolio workspace (applications + pending actions).
        today: Injected current date (ISO ``YYYY-MM-DD``) for the nudge/snooze.
        prefs_path: Optional snooze-prefs path override (tests pass a tmp path).

    Returns:
        A :class:`DashboardView` ready to render.
    """
    pending_lines: list[str] = []
    pending_detail: list[dict[str, str]] = []
    for pa in workspace.pending_actions:
        line = pa.reason or f"Follow up on application {pa.application_id}"
        pending_lines.append(line)
        pending_detail.append(
            {"application_id": pa.application_id, "kind": pa.kind, "reason": line}
        )

    return DashboardView(
        progress_meter=render_progress_meter(state),
        show_nudge=should_show_nudge(state, today=today, prefs_path=prefs_path),
        nudge_message=discovery_nudge_message(),
        pending_actions=pending_lines,
        application_count=len(workspace.applications),
        can_tailor=True,
        can_start_grill=True,
        pending_actions_detail=pending_detail,
    )


class _StLike(Protocol):
    """The minimal Streamlit surface the renderer uses (real or fake)."""

    def title(self, body: str) -> Any: ...
    def caption(self, body: str) -> Any: ...
    def warning(self, body: str) -> Any: ...
    def subheader(self, body: str) -> Any: ...
    def write(self, body: Any) -> Any: ...
    def button(self, label: str) -> Any: ...


def render_dashboard(view: DashboardView, *, st: _StLike) -> None:
    """Render the dashboard via an injected ``st``-like module.

    Thin map from view-model → widgets. The tailor/grill entry points are ALWAYS
    rendered (never gated); the nudge is an informational ``warning`` only.

    Args:
        view: The view-model from :func:`build_dashboard_view`.
        st: A Streamlit-like module (the real ``streamlit`` in the app; a fake in tests).
    """
    st.title("CareerEngine")
    st.caption(view.progress_meter)

    if view.show_nudge:
        st.warning(view.nudge_message)

    st.subheader("Pending actions")
    if view.pending_actions:
        for line in view.pending_actions:
            st.write(f"• {line}")
    else:
        st.write("No pending actions.")

    st.subheader("Your portfolio")
    st.write(f"Tracked applications: {view.application_count}")

    # Entry points — ALWAYS rendered unconditionally (applying/tailoring is
    # never blocked). The can_* view flags document this invariant (asserted in
    # tests); they intentionally do NOT gate rendering here.
    st.subheader("Actions")
    st.button("Start / continue grilling")
    st.button("Tailor a resume")
