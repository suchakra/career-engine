"""Tests for the 14-day pending-action sweep (Phase 2D).

Deterministic: "today" is injected; no wall clock. Covers staleness threshold,
exactly-once flagging, idempotency on re-run, status filtering, and per-user
error isolation.
"""

from __future__ import annotations

from jobs.pending_action_sweep import (
    SweepReport,
    run_sweep,
    sweep_workspace,
)
from schema import Application, ApplicationStatus, UserWorkspace

TODAY = "2026-06-30"


def _applied(applied_on: str, *, company: str = "Acme") -> Application:
    """An APPLIED application submitted on the given date."""
    return Application(company=company, job_title="Engineer", applied_on=applied_on)


# ── Pure core: sweep_workspace ────────────────────────────────────────────────


class TestSweepWorkspace:
    """sweep_workspace flags stale applied applications, idempotently."""

    def test_old_applied_flagged_once(self) -> None:
        """An application applied >14 days ago gets exactly one follow-up marker."""
        ws = UserWorkspace(applications=[_applied("2026-06-01")])  # 29 days
        out = sweep_workspace(ws, today=TODAY)
        assert len(out.pending_actions) == 1
        pa = out.pending_actions[0]
        assert pa.kind == "follow_up"
        assert pa.application_id == str(ws.applications[0].application_id)
        assert pa.created_on == TODAY

    def test_recent_applied_untouched(self) -> None:
        """An application applied within the threshold is not flagged."""
        ws = UserWorkspace(applications=[_applied("2026-06-20")])  # 10 days
        out = sweep_workspace(ws, today=TODAY)
        assert out.pending_actions == []

    def test_boundary_exactly_14_days_not_flagged(self) -> None:
        """Exactly 14 days old is not yet stale (strictly greater than threshold)."""
        ws = UserWorkspace(applications=[_applied("2026-06-16")])  # 14 days
        assert sweep_workspace(ws, today=TODAY).pending_actions == []

    def test_non_applied_status_untouched(self) -> None:
        """Interview/offer/rejected applications are never swept."""
        old = "2026-01-01"
        ws = UserWorkspace(
            applications=[
                Application(company="A", status=ApplicationStatus.INTERVIEW, applied_on=old),
                Application(company="B", status=ApplicationStatus.REJECTED, applied_on=old),
            ]
        )
        assert sweep_workspace(ws, today=TODAY).pending_actions == []

    def test_idempotent_on_rerun(self) -> None:
        """Re-running the sweep does not add a second marker for the same app."""
        ws = UserWorkspace(applications=[_applied("2026-06-01")])
        first = sweep_workspace(ws, today=TODAY)
        second = sweep_workspace(first, today=TODAY)
        assert len(second.pending_actions) == 1

    def test_input_not_mutated(self) -> None:
        """The input workspace is not mutated (pure function)."""
        ws = UserWorkspace(applications=[_applied("2026-06-01")])
        sweep_workspace(ws, today=TODAY)
        assert ws.pending_actions == []

    def test_unparseable_date_skipped(self) -> None:
        """An application with a garbage applied_on date is skipped, not crashed."""
        ws = UserWorkspace(applications=[_applied("not-a-date")])
        assert sweep_workspace(ws, today=TODAY).pending_actions == []


# ── Orchestration: run_sweep ──────────────────────────────────────────────────


class _FakeStore:
    """In-memory WorkspaceStore; one user can be configured to fail on load."""

    def __init__(
        self,
        workspaces: dict[str, UserWorkspace],
        *,
        failing: str | None = None,
        failing_save: str | None = None,
    ) -> None:
        self._ws = workspaces
        self._failing = failing
        self._failing_save = failing_save
        self.saved: dict[str, UserWorkspace] = {}

    def list_user_ids(self) -> list[str]:
        return list(self._ws)

    def load(self, user_id: str) -> UserWorkspace:
        if user_id == self._failing:
            raise RuntimeError("simulated load failure")
        return self._ws[user_id]

    def save(self, user_id: str, workspace: UserWorkspace) -> None:
        if user_id == self._failing_save:
            raise RuntimeError("simulated save failure")
        self.saved[user_id] = workspace


class TestRunSweep:
    """run_sweep persists changes and isolates per-user failures."""

    def test_flags_and_persists_only_changed_users(self) -> None:
        """A stale user is saved; an up-to-date user is not."""
        store = _FakeStore(
            {
                "stale": UserWorkspace(applications=[_applied("2026-06-01")]),
                "fresh": UserWorkspace(applications=[_applied("2026-06-28")]),
            }
        )
        report = run_sweep(store=store, today=TODAY, log=lambda _m: None)
        assert report == SweepReport(
            users_processed=2, users_failed=0, pending_actions_created=1
        )
        assert "stale" in store.saved
        assert "fresh" not in store.saved

    def test_one_user_failure_does_not_abort_sweep(self) -> None:
        """A failing user is counted and logged; others still process."""
        logs: list[str] = []
        store = _FakeStore(
            {
                "bad": UserWorkspace(applications=[_applied("2026-06-01")]),
                "good": UserWorkspace(applications=[_applied("2026-06-01")]),
            },
            failing="bad",
        )
        report = run_sweep(store=store, today=TODAY, log=logs.append)
        assert report.users_failed == 1
        assert report.users_processed == 1
        assert report.pending_actions_created == 1
        assert "good" in store.saved
        assert any("bad" in line for line in logs)

    def test_save_failure_counted_not_credited(self) -> None:
        """A save() failure isolates the user and does not credit a created action."""
        logs: list[str] = []
        store = _FakeStore(
            {"u": UserWorkspace(applications=[_applied("2026-06-01")])},
            failing_save="u",
        )
        report = run_sweep(store=store, today=TODAY, log=logs.append)
        assert report.users_failed == 1
        assert report.users_processed == 0
        assert report.pending_actions_created == 0
        assert "u" not in store.saved
        assert any("u" in line for line in logs)

    def test_rerun_idempotent_across_orchestration(self) -> None:
        """Running the orchestration twice does not duplicate markers."""
        store = _FakeStore({"u": UserWorkspace(applications=[_applied("2026-06-01")])})
        run_sweep(store=store, today=TODAY, log=lambda _m: None)
        # Persist the swept state back, then re-run.
        store._ws["u"] = store.saved["u"]
        report = run_sweep(store=store, today=TODAY, log=lambda _m: None)
        assert report.pending_actions_created == 0
        assert len(store._ws["u"].pending_actions) == 1
