"""Protected portfolio action routes (parity P4b).

Thin transport over the existing portfolio-mutation seams (``web.portfolio_store``):
steer the grill onto an entry, pin/unpin an entry, and delete a STAR story. No new
domain logic.

Async / threadpool discipline (identical to ``routes_write``): endpoints are
``async``; the SYNC session-mutation bridges (``set_grill_frontier`` etc., which own
their own event loop via ``run_async``) run inside
:func:`starlette.concurrency.run_in_threadpool` so they never block the request loop.
Each bridge returns the mutated id, or ``None`` when there is no session / entry to
act on — which we map to 404.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from starlette.concurrency import run_in_threadpool

from api.deps import get_current_user_id, get_session_service
from api.schemas import HighlightRequest
from config import get_settings
from database.firestore_session import FirestoreSessionService
from web.portfolio_store import (
    delete_star_story,
    set_entry_highlight,
    set_grill_frontier,
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
        raise HTTPException(status_code=404, detail="Entry not found.")
    return Response(status_code=204)


@router.delete("/api/story/{story_id}", status_code=204)
async def delete_story(
    story_id: str,
    session_service: FirestoreSessionService = Depends(get_session_service),
    user_id: str = Depends(get_current_user_id),
) -> Response:
    """Delete a STAR story by id (404 when there is no session / no such story)."""
    app_name = get_settings().app_name
    result = await run_in_threadpool(
        delete_star_story,
        session_service,
        app_name=app_name,
        user_id=user_id,
        story_id=story_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="No story to delete.")
    return Response(status_code=204)
