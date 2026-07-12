"""Protected read routes for the API (Phase 10.2).

Three typed, authenticated GET endpoints that WRAP existing read paths — pure
presentation/transport, no domain logic and no contract change:

- ``GET /api/dashboard`` — the progress meter, nudge, pending actions, and
  application count (:func:`web.dashboard.build_dashboard_view`).
- ``GET /api/portfolio`` — the experience timeline with its STAR stories
  (:func:`web.portfolio.build_portfolio_view`).
- ``GET /api/jobs`` — previously-accepted job matches minus dismissed companies
  (:func:`web.jobs.build_jobs_view`).

Every route is protected identically to ``/api/me`` (reuses
:func:`api.deps.get_current_user_id`). Endpoints are ``async``: the discovery
loader is awaited natively (never the ``web.async_runner`` sync bridge / no
``asyncio.run``), and the SYNC store calls run in a threadpool so they never
block the event loop. Read failures degrade to an empty typed payload — a schema
``ContractVersionError`` is the one exception that PROPAGATES (a version mismatch
must not masquerade as an empty, lost workspace).
"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends
from starlette.concurrency import run_in_threadpool

from api.deps import (
    get_current_user_id,
    get_ledger_store,
    get_session_service,
    get_workspace_store,
)
from api.schemas import DashboardResponse, JobsResponse, PortfolioResponse
from config import get_settings
from database.firestore_session import ContractVersionError, FirestoreSessionService
from database.workspace_store import FirestoreWorkspaceStore
from discovery.store import FirestoreLedgerStore
from schema import JobOpportunity, SessionPreferences, UserProfile, UserWorkspace
from web.dashboard import build_dashboard_view
from web.jobs import build_jobs_view
from web.portfolio import build_portfolio_view
from web.session_loader import atry_load_latest_discovery_state

_log = logging.getLogger("career_engine.api")

router = APIRouter()


def _safe_load_workspace(store: FirestoreWorkspaceStore, user_id: str) -> UserWorkspace:
    """Load the workspace, degrading a transient failure to an empty workspace.

    Mirrors the web app's ``_load_workspace``: a :class:`ContractVersionError`
    PROPAGATES (a schema mismatch must not masquerade as an empty, lost
    workspace); any other backend failure falls back to an empty
    :class:`~schema.UserWorkspace` (never a 500). Runs synchronously — the caller
    invokes it via :func:`run_in_threadpool`.
    """
    try:
        return store.load(user_id)
    except ContractVersionError:
        raise
    except Exception:
        _log.warning("could not load workspace; showing an empty view")
        return UserWorkspace()


def _safe_load_jobs(
    store: FirestoreLedgerStore, user_id: str
) -> tuple[list[JobOpportunity], set[str]]:
    """Load accepted jobs + dismissed companies, degrading a fault to empty.

    The read APIs never 500 on a backend fault: a Firestore
    outage/credential/parse failure yields no jobs (an empty list + no
    dismissals) rather than an error, logged generically (no PII, no stack).
    Runs synchronously — the caller invokes it via :func:`run_in_threadpool`.
    (There is no contract-version gate on the ledger, so nothing propagates.)
    """
    try:
        prior = store.list_accepted(user_id)
        hidden = set(store.load_ledger(user_id).rejected_companies)
        return prior, hidden
    except Exception:
        _log.warning("could not load job matches; showing none")
        return [], set()



@router.get("/api/dashboard")
async def dashboard(
    user_id: str = Depends(get_current_user_id),
    session_service: FirestoreSessionService = Depends(get_session_service),
    workspace_store: FirestoreWorkspaceStore = Depends(get_workspace_store),
) -> DashboardResponse:
    """Return the caller's display-ready dashboard. Requires a valid bearer token.

    A missing/failed discovery session degrades to an empty progress meter; a
    transient workspace fault degrades to an empty workspace. A schema
    ``ContractVersionError`` propagates.
    """
    today = date.today().isoformat()
    state = await atry_load_latest_discovery_state(
        session_service,
        app_name=get_settings().app_name,
        user_id=user_id,
        reference_date=today,
    )
    workspace = await run_in_threadpool(_safe_load_workspace, workspace_store, user_id)
    view = build_dashboard_view(state, workspace, today=today)
    return DashboardResponse.from_view(view)


@router.get("/api/portfolio")
async def portfolio(
    user_id: str = Depends(get_current_user_id),
    session_service: FirestoreSessionService = Depends(get_session_service),
) -> PortfolioResponse:
    """Return the caller's display-ready portfolio. Requires a valid bearer token.

    A missing/failed discovery session degrades to an empty portfolio payload.
    """
    today = date.today().isoformat()
    state = await atry_load_latest_discovery_state(
        session_service,
        app_name=get_settings().app_name,
        user_id=user_id,
        reference_date=today,
    )
    view = build_portfolio_view(state)
    return PortfolioResponse.from_view(view)


@router.get("/api/jobs")
async def jobs(
    user_id: str = Depends(get_current_user_id),
    ledger_store: FirestoreLedgerStore = Depends(get_ledger_store),
) -> JobsResponse:
    """Return the caller's persisted job matches. Requires a valid bearer token.

    Shows previously-accepted jobs minus dismissed companies. No persisted jobs —
    or a transient ledger fault — yields an empty typed payload (never a 500).
    """
    prior, hidden_companies = await run_in_threadpool(_safe_load_jobs, ledger_store, user_id)
    view = build_jobs_view(None, prior=prior, hidden_companies=hidden_companies)
    return JobsResponse.from_view(view)


# ── Profile + preferences reads ───────────────────────────────────────────────
#
# The 10.3 write endpoints (``POST /api/profile`` / ``PUT /api/preferences``) shipped
# without their read twins, so the client had no way to hydrate the forms: they mounted
# empty, and a saved profile looked like it had never persisted. These are the missing
# reads over the SAME store seams the write endpoints already re-read through.


@router.get("/api/profile")
async def profile(
    user_id: str = Depends(get_current_user_id),
    workspace_store: FirestoreWorkspaceStore = Depends(get_workspace_store),
) -> UserProfile:
    """Return the caller's persisted résumé-header profile (empty for a new user).

    Reads through :func:`_safe_load_workspace`, so it obeys this module's contract:
    a transient store fault degrades to an empty profile (never a 500) while a
    ``ContractVersionError`` still propagates. The defensive copy matches
    :func:`web.profile_store.load_profile` — a caller mutating the result must not
    write through to a cached workspace instance.
    """
    workspace = await run_in_threadpool(_safe_load_workspace, workspace_store, user_id)
    return workspace.profile.model_copy(deep=True)


@router.get("/api/preferences")
async def preferences(
    user_id: str = Depends(get_current_user_id),
    workspace_store: FirestoreWorkspaceStore = Depends(get_workspace_store),
) -> SessionPreferences:
    """Return the caller's persisted discovery rubric (empty for a new user).

    Same degrade-to-empty contract as :func:`profile` above.
    """
    workspace = await run_in_threadpool(_safe_load_workspace, workspace_store, user_id)
    return workspace.discovery_preferences.model_copy(deep=True)
