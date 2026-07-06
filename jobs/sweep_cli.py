"""CLI entrypoint for the 14-day pending-action sweep (Cloud Run Job path).

Primary execution path: Cloud Scheduler → Cloud Run Job → `career-engine sweep`.
The HTTP path (sweep_endpoint.py) is retained as an alternative trigger.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from jobs.pending_action_sweep import WorkspaceStore, run_sweep

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SweepResult:
    workspaces_processed: int
    actions_triggered: int


def resolve_sweep_store() -> WorkspaceStore:
    """Return a FirestoreWorkspaceStore; fall back to in-memory with a warning if Firestore unavailable."""
    try:
        from database.workspace_store import FirestoreWorkspaceStore

        return FirestoreWorkspaceStore()
    except Exception as exc:
        logger.warning(
            "Firestore unavailable (%s); using in-memory store (no-op sweep).", exc
        )
        from database.workspace_store import InMemoryWorkspaceStore

        return InMemoryWorkspaceStore()


def run_sweep_command(
    store: WorkspaceStore | None = None, today: str | None = None
) -> SweepResult:
    """Run the sweep and return counts. Called by the CLI entry point."""
    if store is None:
        store = resolve_sweep_store()
    if today is None:
        today = date.today().isoformat()
    report = run_sweep(store=store, today=today)
    logger.info(
        "Swept %d workspaces, %d actions triggered.",
        report.users_processed,
        report.pending_actions_created,
    )
    return SweepResult(
        workspaces_processed=report.users_processed,
        actions_triggered=report.pending_actions_created,
    )
