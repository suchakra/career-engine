"""Tests for jobs/sweep_cli.py (WS 8C).

Two required named tests:
- test_sweep_cli_calls_run_sweep
- test_sweep_cli_store_fallback
"""

from __future__ import annotations

from unittest.mock import patch

from database.workspace_store import InMemoryWorkspaceStore
from jobs.pending_action_sweep import SweepReport
from jobs.sweep_cli import SweepResult, resolve_sweep_store, run_sweep_command


def test_sweep_cli_calls_run_sweep() -> None:
    """run_sweep_command delegates to run_sweep and maps SweepReport to SweepResult."""
    store = InMemoryWorkspaceStore()
    mock_report = SweepReport(users_processed=3, users_failed=0, pending_actions_created=2)
    with patch("jobs.sweep_cli.run_sweep", return_value=mock_report) as mock_sweep:
        result = run_sweep_command(store=store, today="2026-07-06")

    mock_sweep.assert_called_once_with(store=store, today="2026-07-06")
    assert result == SweepResult(workspaces_processed=3, actions_triggered=2)


def test_sweep_cli_store_fallback() -> None:
    """resolve_sweep_store falls back to InMemoryWorkspaceStore when Firestore is unavailable."""
    with patch(
        "database.workspace_store.FirestoreWorkspaceStore",
        side_effect=RuntimeError("no credentials"),
    ):
        store = resolve_sweep_store()

    assert isinstance(store, InMemoryWorkspaceStore)
