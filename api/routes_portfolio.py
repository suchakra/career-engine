"""Protected portfolio action routes (parity P4b / P5).

Thin transport over the existing portfolio-mutation seams (``web.portfolio_store``):
steer the grill onto an entry, pin/unpin an entry, edit an experience bullet, and
delete a STAR story. No new domain logic.

Async / threadpool discipline (identical to ``routes_write``): endpoints are
``async``; the SYNC session-mutation bridges (``set_grill_frontier`` etc., which own
their own event loop via ``run_async``) run inside
:func:`starlette.concurrency.run_in_threadpool` so they never block the request loop.

Each bridge returns the mutated session id, or ``None`` — which we map to 404. The
``None`` condition differs per bridge (see ``web.portfolio_store``): ``grill`` and
``delete_star_story`` return ``None`` only when the user has *no session*, while
``highlight`` also returns ``None`` when the target entry is absent. Deleting a
missing story is an idempotent no-op that still returns the session id → 204.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from starlette.concurrency import run_in_threadpool

from api.deps import get_current_user_id, get_session_service
from api.schemas import BulletAddRequest, BulletEditRequest, HighlightRequest
from config import get_settings
from database.firestore_session import FirestoreSessionService
from web.portfolio_store import (
    add_entry_bullet,
    delete_star_story,
    set_entry_highlight,
    set_grill_frontier,
    update_entry_bullet,
)

router = APIRouter()


@router.post("/api/experience/{entry_id}/grill", status_code=204)
async def grill_entry(
    entry_id: str,
    session_service: FirestoreSessionService = Depends(get_session_service),
    user_id: str = Depends(get_current_user_id),
) -> Response:
    """Pin the grill frontier to ``entry_id`` so the next grill turn focuses on it."""
    app_name = get_settings().app_name
    result = await run_in_threadpool(
        set_grill_frontier,
        session_service,
        app_name=app_name,
        user_id=user_id,
        entry_id=entry_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="No session to steer.")
    return Response(status_code=204)


@router.post("/api/experience/{entry_id}/highlight", status_code=204)
async def highlight_entry(
    entry_id: str,
    body: HighlightRequest,
    session_service: FirestoreSessionService = Depends(get_session_service),
    user_id: str = Depends(get_current_user_id),
) -> Response:
    """Flip an entry's ``highlighted`` (pin) flag — pinned entries are always tailored."""
    app_name = get_settings().app_name
    result = await run_in_threadpool(
        set_entry_highlight,
        session_service,
        app_name=app_name,
        user_id=user_id,
        entry_id=entry_id,
        highlighted=body.highlighted,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="No such entry, or no active session.")
    return Response(status_code=204)


@router.post("/api/experience/{entry_id}/bullet", status_code=204)
async def add_bullet(
    entry_id: str,
    body: BulletAddRequest,
    session_service: FirestoreSessionService = Depends(get_session_service),
    user_id: str = Depends(get_current_user_id),
) -> Response:
    """Append a new bullet to an experience — add a line without re-grilling the entry.

    Like the PATCH twin below, the bridge treats a missing entry as a logged no-op, so
    the 404 fires only when the user has no discovery session at all.
    """
    app_name = get_settings().app_name
    result = await run_in_threadpool(
        add_entry_bullet,
        session_service,
        app_name=app_name,
        user_id=user_id,
        entry_id=entry_id,
        text=body.text,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="No active session.")
    return Response(status_code=204)


@router.patch("/api/experience/{entry_id}/bullet", status_code=204)
async def edit_bullet(
    entry_id: str,
    body: BulletEditRequest,
    session_service: FirestoreSessionService = Depends(get_session_service),
    user_id: str = Depends(get_current_user_id),
) -> Response:
    """Edit one existing bullet on an experience in place.

    The bullet is addressed by its stable ``bullet_id`` (v2.9.0), never by array index —
    an index shifts under any concurrent insert or delete, so a slow client could edit
    the wrong line. The bridge treats a missing entry or an UNKNOWN ``bullet_id`` as a
    logged no-op (it never raises), so those still return 204. The 404 fires only when
    the user has no discovery session at all (bridge returns ``None``).
    """
    app_name = get_settings().app_name
    result = await run_in_threadpool(
        update_entry_bullet,
        session_service,
        app_name=app_name,
        user_id=user_id,
        entry_id=entry_id,
        bullet_id=body.bullet_id,
        new_text=body.new_text,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="No active session.")
    return Response(status_code=204)


@router.delete("/api/story/{story_id}", status_code=204)
async def delete_story(
    story_id: str,
    session_service: FirestoreSessionService = Depends(get_session_service),
    user_id: str = Depends(get_current_user_id),
) -> Response:
    """Delete a STAR story by id.

    Idempotent: a missing ``story_id`` is a no-op that still returns 204. The 404 fires
    only when the user has no discovery session at all (bridge returns ``None``).
    """
    app_name = get_settings().app_name
    result = await run_in_threadpool(
        delete_star_story,
        session_service,
        app_name=app_name,
        user_id=user_id,
        story_id=story_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="No active session.")
    return Response(status_code=204)
