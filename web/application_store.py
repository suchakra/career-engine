"""Save-as-tracked-application seam (Phase 5B).

The Tailor produces a résumé for a specific JD; this is the write path that records
that as an :class:`schema.Application` on the user's :class:`schema.UserWorkspace`,
so it shows in the dashboard "Tracked applications" and enters the 14-day
follow-up sweep (``jobs/pending_action_sweep``). Closes the apply → track →
follow-up loop.

Pure + injectable: :func:`build_application` has no IO; :func:`save_tailored_application`
takes any store exposing sync ``load(user_id)`` / ``save(user_id, workspace)`` (the
real :class:`database.workspace_store.FirestoreWorkspaceStore` or a test double), so
the logic is unit-tested without GCP. No secrets are written — only what the user
tailored against (public JD text + their own résumé JSON).
"""

from __future__ import annotations

from typing import Protocol

from schema import Application, ApplicationStatus, UserWorkspace


class WorkspaceStore(Protocol):
    """Sync workspace persistence surface (matches FirestoreWorkspaceStore)."""

    def load(self, user_id: str) -> UserWorkspace:
        """Return the user's workspace (empty for a new user)."""
        ...

    def save(self, user_id: str, workspace: UserWorkspace) -> None:
        """Persist the user's workspace."""
        ...


def build_application(
    *,
    company: str,
    job_title: str,
    jd_text: str,
    tailored_resume_json: str,
    applied_on: str,
    status: ApplicationStatus = ApplicationStatus.APPLIED,
) -> Application:
    """Construct an :class:`Application` from a completed tailor (no IO).

    ``applied_on`` is the injected clock date (``YYYY-MM-DD``) that drives the
    14-day sweep — passed from the UI boundary, never read from ``datetime.now()``.
    """
    return Application(
        company=company.strip(),
        job_title=job_title.strip(),
        status=status,
        applied_on=applied_on,
        jd_text=jd_text,
        tailored_resume_json=tailored_resume_json,
    )


def save_tailored_application(
    store: WorkspaceStore,
    *,
    user_id: str,
    company: str,
    job_title: str,
    jd_text: str,
    tailored_resume_json: str,
    applied_on: str,
) -> Application:
    """Append a tailored résumé as a tracked application and persist it.

    Loads the workspace, appends the new :class:`Application`, and saves — a
    read-modify-write that reuses the existing workspace document (so it coexists
    with the async sweep's pending actions). Returns the created application.

    Args:
        store: Sync workspace store (real or test double).
        user_id: Owner of the workspace.
        company / job_title: The employer + role this résumé targets.
        jd_text: The cleaned job description tailored against.
        tailored_resume_json: The tailored résumé variant (``StructuredResume`` JSON).
        applied_on: ISO date the application was recorded (injected clock).

    Returns:
        The persisted :class:`Application`.
    """
    application = build_application(
        company=company,
        job_title=job_title,
        jd_text=jd_text,
        tailored_resume_json=tailored_resume_json,
        applied_on=applied_on,
    )
    workspace = store.load(user_id)
    workspace.applications.append(application)
    store.save(user_id, workspace)
    return application


__all__ = ["WorkspaceStore", "build_application", "save_tailored_application"]
