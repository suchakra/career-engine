"""Tests for progressive-discovery CLI surfaces (Phase 1.5 / 1.5-DISCOVERY).

Covers the progress meter, the consent-respecting nudge, snooze (local prefs,
injected "today"), and the backward return loop.  Core invariant: discovery is
a NUDGE, never a gate — applying/tailoring always proceeds.

All tests are deterministic: ``reference_date`` is fixed on the state and
"today" is injected; snooze prefs are written to a tmp path.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import cli.prefs as prefs
from cli.app import (
    DiscoverySession,
    emit_nudge_if_needed,
    has_resumable_work,
    render_progress_meter,
    resumable_entries,
    run_return_loop,
    should_show_nudge,
)
from schema import CareerEngineState, Entry, EntryStatus, ExperienceType

REF_DATE = "2026-06-29"


def _entry(
    *,
    title: str,
    start: str,
    end: str = "",
    status: EntryStatus = EntryStatus.NEEDS_QUANTIFYING,
    type_: ExperienceType = ExperienceType.FULL_TIME,
) -> Entry:
    """Build a test Entry."""
    return Entry(
        type=type_, title=title, org="Org", start_date=start, end_date=end, status=status
    )


def _incomplete_state() -> CareerEngineState:
    """Recent window with one grilled + one pending entry → 50%, not complete."""
    return CareerEngineState(
        reference_date=REF_DATE,
        work_timeline=[
            _entry(title="Current", start="2022", end="", status=EntryStatus.GRILLED),
            _entry(title="Recent", start="2023", end="2024", status=EntryStatus.NEEDS_QUANTIFYING),
        ],
    )


def _complete_state() -> CareerEngineState:
    """Recent window fully grilled → 100%, complete."""
    return CareerEngineState(
        reference_date=REF_DATE,
        work_timeline=[
            _entry(title="Current", start="2022", end="", status=EntryStatus.GRILLED),
        ],
    )


# ── Progress meter ────────────────────────────────────────────────────────────


class TestProgressMeter:
    """The meter renders correct completeness % and portfolio depth."""

    def test_renders_percent_and_depth(self) -> None:
        """50% documented (1 of 2 window entries) and 4 yrs depth (2026-2022)."""
        meter = render_progress_meter(_incomplete_state())
        assert "50% documented" in meter
        assert "4 yrs" in meter

    def test_full_window_renders_100(self) -> None:
        """A fully-grilled window renders 100%."""
        assert "100% documented" in render_progress_meter(_complete_state())

    def test_empty_state_is_zero(self) -> None:
        """No entries / no reference_date → 0% and 0 yrs (no crash)."""
        meter = render_progress_meter(CareerEngineState())
        assert "0% documented" in meter
        assert "0 yrs" in meter


# ── Nudge: shown / hidden / snoozed ───────────────────────────────────────────


class TestNudge:
    """The nudge appears only when the window is incomplete and not snoozed."""

    def test_shown_when_incomplete(self, tmp_path: Path) -> None:
        """Incomplete window, not snoozed → nudge shown."""
        prefs_path = tmp_path / "prefs.json"
        lines: list[str] = []
        shown = emit_nudge_if_needed(
            _incomplete_state(), today=REF_DATE, prefs_path=prefs_path, out=lines.append
        )
        assert shown is True
        assert any("stronger" in line for line in lines)

    def test_not_shown_when_complete(self, tmp_path: Path) -> None:
        """Complete window → no nudge."""
        prefs_path = tmp_path / "prefs.json"
        assert should_show_nudge(_complete_state(), today=REF_DATE, prefs_path=prefs_path) is False

    def test_not_shown_when_snoozed(self, tmp_path: Path) -> None:
        """Incomplete window but snoozed into the future → no nudge."""
        prefs_path = tmp_path / "prefs.json"
        prefs.set_snooze_until("2026-07-15", path=prefs_path)
        assert should_show_nudge(_incomplete_state(), today=REF_DATE, prefs_path=prefs_path) is False

    def test_snooze_expires(self, tmp_path: Path) -> None:
        """Once 'today' reaches the snooze date, the nudge returns."""
        prefs_path = tmp_path / "prefs.json"
        prefs.set_snooze_until("2026-07-15", path=prefs_path)
        # Before the snooze date → suppressed
        assert prefs.is_snoozed("2026-07-14", path=prefs_path) is True
        # On/after the snooze date → no longer suppressed
        assert prefs.is_snoozed("2026-07-15", path=prefs_path) is False
        assert should_show_nudge(_incomplete_state(), today="2026-07-16", prefs_path=prefs_path) is True

    def test_nudge_is_informational_only_never_gates(self, tmp_path: Path) -> None:
        """The nudge helper returns a bool and never raises/blocks.

        This is the mechanism by which apply/tailor is NEVER gated: the only
        window check on those paths is this emit call, which is non-blocking
        (returns True to say "shown" but the caller's action proceeds).
        """
        prefs_path = tmp_path / "prefs.json"
        result = emit_nudge_if_needed(
            _incomplete_state(), today=REF_DATE, prefs_path=prefs_path, out=lambda _s: None
        )
        assert result is True  # nudge emitted, but flow continues normally


# ── Return loop ────────────────────────────────────────────────────────────────


class _FakeSession:
    """A minimal stand-in for DiscoverySession driving the return loop."""

    def __init__(self, state: CareerEngineState) -> None:
        self._state = state
        self.advance_calls = 0

    async def current_state(self) -> CareerEngineState:
        return self._state

    async def advance(self) -> None:
        self.advance_calls += 1


class TestReturnLoop:
    """Older pending entries are offered; accepting drives one backward turn."""

    def test_resumable_excludes_frontier_and_newer(self) -> None:
        """resumable_entries returns pending entries older than the frontier."""
        frontier = _entry(title="Frontier", start="2022", status=EntryStatus.NEEDS_QUANTIFYING)
        older = _entry(title="Older", start="2019", status=EntryStatus.NEEDS_QUANTIFYING)
        state = CareerEngineState(
            reference_date=REF_DATE,
            work_timeline=[frontier, older],
            grill_frontier=str(frontier.entry_id),
        )
        titles = [e.title for e in resumable_entries(state)]
        assert titles == ["Older"]
        assert has_resumable_work(state) is True

    def test_no_resumable_when_all_done(self) -> None:
        """No pending entries → nothing to resume."""
        state = CareerEngineState(
            reference_date=REF_DATE,
            work_timeline=[_entry(title="Done", start="2022", status=EntryStatus.GRILLED)],
        )
        assert has_resumable_work(state) is False

    async def test_accept_drives_one_backward_turn(self) -> None:
        """Accepting drives exactly one grill turn through the session."""
        frontier = _entry(title="Frontier", start="2022", status=EntryStatus.NEEDS_QUANTIFYING)
        older = _entry(title="Older", start="2019", status=EntryStatus.NEEDS_QUANTIFYING)
        state = CareerEngineState(
            reference_date=REF_DATE,
            work_timeline=[frontier, older],
            grill_frontier=str(frontier.entry_id),
        )
        fake = _FakeSession(state)
        drove = await run_return_loop(cast(DiscoverySession, fake), accept=True)
        assert drove is True
        assert fake.advance_calls == 1

    async def test_decline_proceeds_without_grilling(self) -> None:
        """Declining drives no turn and proceeds cleanly."""
        state = CareerEngineState(
            reference_date=REF_DATE,
            work_timeline=[
                _entry(title="Frontier", start="2022", status=EntryStatus.NEEDS_QUANTIFYING),
                _entry(title="Older", start="2019", status=EntryStatus.NEEDS_QUANTIFYING),
            ],
        )
        fake = _FakeSession(state)
        drove = await run_return_loop(cast(DiscoverySession, fake), accept=False)
        assert drove is False
        assert fake.advance_calls == 0

    async def test_no_resumable_means_no_turn(self) -> None:
        """With no resumable work, accepting still drives nothing."""
        state = CareerEngineState(
            reference_date=REF_DATE,
            work_timeline=[_entry(title="Done", start="2022", status=EntryStatus.GRILLED)],
        )
        fake = _FakeSession(state)
        drove = await run_return_loop(cast(DiscoverySession, fake), accept=True)
        assert drove is False
        assert fake.advance_calls == 0


# ── Snooze state lives OUTSIDE CareerEngineState ──────────────────────────────


class TestNoStateMutation:
    """UI / snooze state must not live on the contract object."""

    def test_state_has_no_ui_fields(self) -> None:
        """CareerEngineState carries no snooze / UI field."""
        assert "snooze_until" not in CareerEngineState.model_fields

    def test_snooze_persists_to_file_not_state(self, tmp_path: Path) -> None:
        """Snoozing writes to the local prefs file, not to any state object."""
        prefs_path = tmp_path / "prefs.json"
        prefs.set_snooze_until("2026-08-01", path=prefs_path)
        assert prefs_path.exists()
        assert prefs.get_snooze_until(path=prefs_path) == "2026-08-01"


# ── No hardcoded model names ──────────────────────────────────────────────────


class TestNoHardcodedModelNames:
    """cli/ must request capabilities, never name a model."""

    def test_no_gemini_literal_in_cli(self) -> None:
        """No 'gemini-' literal in the CLI modules touched by this workstream."""
        root = Path(__file__).resolve().parent.parent
        for rel in ("cli/app.py", "cli/prefs.py", "cli/session.py", "main.py"):
            assert "gemini-" not in (root / rel).read_text(encoding="utf-8"), rel
