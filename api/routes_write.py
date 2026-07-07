"""Protected write routes for the API (Phase 10.3).

Four typed, authenticated write endpoints that WRAP existing store write-seams —
pure presentation/transport, no domain logic and no contract change (the
``schema.py`` domain models are the AD-16.3 wire contract; importing/returning
them changes nothing):

- ``POST /api/profile`` — persist a :class:`schema.UserProfile` and return the
  re-read persisted profile (:func:`web.profile_store.save_profile` / ``load_profile``).
- ``PUT /api/preferences`` — persist a :class:`schema.SessionPreferences` and return
  the re-read value (:func:`web.preferences_store.save_discovery_preferences` /
  ``load_discovery_preferences``).
- ``POST /api/applications`` — record a tailored application and return the created
  :class:`schema.Application` (:func:`web.application_store.save_tailored_application`).
- ``POST /api/experience`` — append a manual :class:`schema.Entry` to the caller's
  canonical discovery session (:func:`web.portfolio_store.aadd_manual_entry`) and
  return a confirmation re-read from the session.

Every route is protected identically to ``/api/me`` (reuses
:func:`api.deps.get_current_user_id`). FastAPI validates each request body against
its Pydantic model automatically, so a malformed body yields 422 for free.

Async / threadpool discipline (identical to ``routes_read``): endpoints are
``async``. The SYNC workspace-store calls (profile/preferences/applications) run
inside :func:`starlette.concurrency.run_in_threadpool` so they never block the
event loop; the ASYNC session write + re-read (experience) are awaited natively.
Never the ``web.async_runner`` sync bridge / no ``asyncio.run``.

Transactional caveat (ARCHITECTURE §8): the workspace stores do a full-document
``set`` (single-writer caveat — a concurrent writer between load and save would be
overwritten). This layer only REUSES those seams; adding transactions /
``ArrayUnion`` / locking is the deferred multi-user hardening, out of scope here.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from starlette.concurrency import run_in_threadpool

from api.deps import (
    get_current_user_id,
    get_session_service,
    get_workspace_store,
)
from api.schemas import ApplicationWriteRequest, ExperienceWriteResponse
from config import get_settings
from database.firestore_session import FirestoreSessionService
from database.workspace_store import FirestoreWorkspaceStore
from schema import Application, Entry, SessionPreferences, UserProfile
from web.application_store import save_tailored_application
from web.portfolio_store import aadd_manual_entry
from web.preferences_store import load_discovery_preferences, save_discovery_preferences
from web.profile_store import load_profile, save_profile
from web.session_loader import atry_load_latest_discovery_state

router = APIRouter()


@router.post("/api/profile")
async def save_profile_endpoint(
    body: UserProfile,
    user_id: str = Depends(get_current_user_id),
    workspace_store: FirestoreWorkspaceStore = Depends(get_workspace_store),
) -> UserProfile:
    """Persist the caller's résumé-header profile and return the re-read value.

    Requires a valid bearer token. The sync store write + re-read run in a
    threadpool. Returns the profile as it was persisted (round-trip), so the
    client sees exactly what was stored.
    """
    await run_in_threadpool(save_profile, workspace_store, user_id=user_id, profile=body)
    return await run_in_threadpool(load_profile, workspace_store, user_id=user_id)


@router.put("/api/preferences")
async def save_preferences_endpoint(
    body: SessionPreferences,
    user_id: str = Depends(get_current_user_id),
    workspace_store: FirestoreWorkspaceStore = Depends(get_workspace_store),
) -> SessionPreferences:
    """Persist the caller's discovery preferences and return the re-read value.

    Requires a valid bearer token. The sync store write + re-read run in a
    threadpool. Returns the preferences as they were persisted (round-trip).
    """
    await run_in_threadpool(
        save_discovery_preferences, workspace_store, user_id=user_id, preferences=body
    )
    return await run_in_threadpool(
        load_discovery_preferences, workspace_store, user_id=user_id
    )


@router.post("/api/applications")
async def save_application_endpoint(
    body: ApplicationWriteRequest,
    user_id: str = Depends(get_current_user_id),
    workspace_store: FirestoreWorkspaceStore = Depends(get_workspace_store),
) -> Application:
    """Record a tailored application and return the created :class:`Application`.

    Requires a valid bearer token. ``applied_on`` is the injected clock
    (``date.today()``) computed at this boundary — never read inside the store. The
    sync store write runs in a threadpool.
    """
    applied_on = date.today().isoformat()
    return await run_in_threadpool(
        save_tailored_application,
        workspace_store,
        user_id=user_id,
        company=body.company,
        job_title=body.job_title,
        jd_text=body.jd_text,
        tailored_resume_json=body.tailored_resume_json,
        applied_on=applied_on,
    )


@router.post("/api/experience")
async def add_experience_endpoint(
    body: Entry,
    user_id: str = Depends(get_current_user_id),
    session_service: FirestoreSessionService = Depends(get_session_service),
) -> ExperienceWriteResponse:
    """Append a manual experience to the caller's canonical discovery session.

    Requires a valid bearer token. ``reference_date`` is the injected clock
    (``date.today()``) computed at this boundary. The async session write and the
    subsequent best-effort re-read are awaited natively (no sync bridge). The
    response confirms the persisted entry re-read from the session; if the re-read
    can't find it (or the session can't be loaded), the ``entry_id`` is still echoed
    with the submitted ``title``/``org`` rather than a 500.
    """
    today = date.today().isoformat()
    app_name = get_settings().app_name
    await aadd_manual_entry(
        session_service,
        app_name=app_name,
        user_id=user_id,
        reference_date=today,
        entry=body,
    )
    state = await atry_load_latest_discovery_state(
        session_service,
        app_name=app_name,
        user_id=user_id,
        reference_date=today,
    )
    persisted = next(
        (e for e in state.work_timeline if str(e.entry_id) == str(body.entry_id)),
        None,
    )
    if persisted is not None:
        return ExperienceWriteResponse(
            entry_id=str(persisted.entry_id),
            title=persisted.title,
            org=persisted.org,
            entry_count=len(state.work_timeline),
        )
    return ExperienceWriteResponse(
        entry_id=str(body.entry_id),
        title=body.title,
        org=body.org,
        entry_count=len(state.work_timeline),
    )
