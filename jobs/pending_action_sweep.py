"""14-day pending-action sweep (ARCHITECTURE §8).

Cloud Scheduler → Cloud Run job. For each user's workspace, any application in
``applied`` status older than the threshold (14 days) gets a ``follow_up``
:class:`~schema.PendingAction` marker, surfaced on the dashboard.

Design:
- The core (:func:`sweep_workspace`) is a PURE function
  ``(UserWorkspace, today) -> UserWorkspace`` — deterministic, idempotent, no
  clock access (``today`` is injected at the boundary, never ``datetime.now()``
  in logic).  Idempotent: it never adds a second ``follow_up`` marker for an
  application that already has one.
- The orchestration (:func:`run_sweep`) iterates a :class:`WorkspaceStore`,
  applies the pure core, and persists changes — ISOLATING per-user failures so
  one bad record never aborts the whole sweep.

The optional follow-up *suggestion* draft (an LLM call) is intentionally NOT
implemented here; when added it MUST resolve the user's key per-user via the
KeyVault/Secret Manager (never a shared key, never Firestore) — see §5/§8.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from schema import ApplicationStatus, PendingAction, UserWorkspace

DEFAULT_THRESHOLD_DAYS = 14
_FOLLOW_UP = "follow_up"


def _days_between(start_iso: str, end_iso: str) -> int | None:
    """Whole days from ``start_iso`` to ``end_iso`` (ISO dates); None if unparseable.

    Pure date arithmetic on the given strings — does not read the wall clock.
    """
    try:
        return (date.fromisoformat(end_iso) - date.fromisoformat(start_iso)).days
    except ValueError:
        return None


def sweep_workspace(
    workspace: UserWorkspace,
    *,
    today: str,
    threshold_days: int = DEFAULT_THRESHOLD_DAYS,
) -> UserWorkspace:
    """Return a workspace with follow-up markers for stale ``applied`` applications.

    An application is *stale* when its ``status`` is ``applied`` and it was
    applied more than ``threshold_days`` before ``today``.  Idempotent: an
    application that already has a ``follow_up`` pending action is skipped, so
    repeated runs never duplicate markers.

    Args:
        workspace: The user's workspace.
        today: Injected current date (ISO ``YYYY-MM-DD``).
        threshold_days: Age in days beyond which an applied app is flagged.

    Returns:
        A new ``UserWorkspace`` (the input is not mutated).
    """
    already_flagged = {
        pa.application_id for pa in workspace.pending_actions if pa.kind == _FOLLOW_UP
    }
    new_actions = list(workspace.pending_actions)

    for app in workspace.applications:
        if app.status != ApplicationStatus.APPLIED:
            continue
        app_id = str(app.application_id)
        if app_id in already_flagged:
            continue  # idempotent — already has a follow-up marker
        age = _days_between(app.applied_on, today)
        if age is None or age <= threshold_days:
            continue
        new_actions.append(
            PendingAction(
                application_id=app_id,
                kind=_FOLLOW_UP,
                reason=(
                    f"Applied {age} days ago to "
                    f"{app.job_title or 'a role'} at {app.company or 'a company'} "
                    "with no update — consider a follow-up."
                ),
                created_on=today,
            )
        )

    return workspace.model_copy(update={"pending_actions": new_actions})


class WorkspaceStore(Protocol):
    """Minimal persistence surface the sweep needs (Firestore-backed in prod)."""

    def list_user_ids(self) -> list[str]:
        """Return the user_ids whose workspaces should be swept."""
        ...

    def load(self, user_id: str) -> UserWorkspace:
        """Load a user's workspace."""
        ...

    def save(self, user_id: str, workspace: UserWorkspace) -> None:
        """Persist a user's workspace."""
        ...


@dataclass(frozen=True)
class SweepReport:
    """Outcome of a sweep run (for logging/observability)."""

    users_processed: int
    users_failed: int
    pending_actions_created: int


def run_sweep(
    *,
    store: WorkspaceStore,
    today: str,
    threshold_days: int = DEFAULT_THRESHOLD_DAYS,
    log: Callable[[str], None] = print,
) -> SweepReport:
    """Run the sweep across all user workspaces, isolating per-user failures.

    A failure loading/sweeping/saving one user is logged with user-safe context
    (no secrets) and counted, but never aborts the rest of the sweep.

    Args:
        store: The workspace persistence surface.
        today: Injected current date (ISO ``YYYY-MM-DD``).
        threshold_days: Staleness threshold passed to :func:`sweep_workspace`.
        log: Sink for user-safe log lines.

    Returns:
        A :class:`SweepReport` summarising the run.
    """
    processed = 0
    failed = 0
    created = 0

    for user_id in store.list_user_ids():
        try:
            workspace = store.load(user_id)
            before = len(workspace.pending_actions)
            updated = sweep_workspace(
                workspace, today=today, threshold_days=threshold_days
            )
            added = len(updated.pending_actions) - before
            if added > 0:
                store.save(user_id, updated)
            created += added
            processed += 1
        except Exception as exc:  # isolate per-user failure
            failed += 1
            log(f"pending-action sweep failed for user {user_id}: {type(exc).__name__}: {exc}")

    return SweepReport(
        users_processed=processed,
        users_failed=failed,
        pending_actions_created=created,
    )
