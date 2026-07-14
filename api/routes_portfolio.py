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

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from starlette.concurrency import run_in_threadpool

from api.deps import get_current_user_id, get_discovery_session, get_session_service
from api.schemas import (
    AcceptBulletsRequest,
    BulletAddRequest,
    BulletAddResponse,
    BulletEditRequest,
    BulletSkipRequest,
    CopyProposalResponse,
    CopyProposalsResponse,
    HighlightRequest,
)
from cli.app import DiscoverySession
from config import get_settings
from database.firestore_session import FirestoreSessionService
from web.copywriter import accept as accept_proposal
from web.copywriter import copywrite_entry
from web.portfolio_store import (
    accept_bullets,
    add_entry_bullet,
    delete_entry,
    delete_entry_bullet,
    delete_star_story,
    set_bullet_skipped,
    set_entry_highlight,
    set_grill_frontier,
    update_entry_bullet,
)
from web.session_loader import atry_load_latest_discovery_state

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


@router.post("/api/experience/{entry_id}/bullet", status_code=201)
async def add_bullet(
    entry_id: str,
    body: BulletAddRequest,
    session_service: FirestoreSessionService = Depends(get_session_service),
    user_id: str = Depends(get_current_user_id),
) -> BulletAddResponse:
    """Append a new bullet to an experience — add a line without re-grilling the entry.

    Like the PATCH twin below, the bridge treats a missing entry as a logged no-op, so
    the 404 fires only when the user has no discovery session at all.

    With ``derived_from_story_id`` (CQ-6b) the new bullet becomes *the résumé line for that
    story*, and the assembler renders it instead of the raw ``story.result``. That link is
    validated HERE, because the store cannot: the story must exist, **belong to this entry**,
    and be ``metrics_validated`` (422 otherwise) — a bullet born with an unearned link would
    read as covered without ever having been grilled, the false QUANTIFIED that AD-18.5 calls
    the worst error coverage can make. And a story that ALREADY has a live bullet speaking for
    it is a **409**: the client is acting on a stale preview (someone accepted a copywriter
    rewrite of this very line meanwhile), and minting a second bullet claiming the same story
    would put the achievement on the résumé twice.
    """
    app_name = get_settings().app_name
    if body.derived_from_story_id:
        state = await atry_load_latest_discovery_state(
            session_service,
            app_name=app_name,
            user_id=user_id,
            reference_date=date.today().isoformat(),
        )
        entry = next(
            (e for e in state.work_timeline if str(e.entry_id) == entry_id), None
        )
        story = next(
            (
                s
                for s in state.extracted_star_stories
                if str(s.story_id) == body.derived_from_story_id
            ),
            None,
        )
        if entry is None or story is None or story.entry_id != entry_id:
            raise HTTPException(
                status_code=422, detail="Unknown story for this experience."
            )
        if not story.metrics_validated:
            raise HTTPException(
                status_code=422, detail="That story has no validated metric."
            )
        if any(b.derived_from_story_id == body.derived_from_story_id for b in entry.bullets):
            raise HTTPException(
                status_code=409,
                detail="This line has already been rewritten elsewhere. Reload to see it.",
            )

    result = await run_in_threadpool(
        add_entry_bullet,
        session_service,
        app_name=app_name,
        user_id=user_id,
        entry_id=entry_id,
        text=body.text,
        derived_from_story_id=body.derived_from_story_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="No active session.")
    if not result.bullet_id:
        # The store treats an unknown entry as a logged no-op. Reporting that as 201-with-an-
        # empty-id would tell the client its overwrite succeeded: it would show "saved to
        # portfolio", offer an Undo that deletes nothing, and hide the fact that the entry had
        # been removed in another tab — exactly the stale-preview case the 409 exists for.
        raise HTTPException(status_code=404, detail="No such experience.")
    return BulletAddResponse(bullet_id=result.bullet_id)


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


@router.delete("/api/experience/{entry_id}/bullet/{bullet_id}", status_code=204)
async def remove_bullet(
    entry_id: str,
    bullet_id: str,
    session_service: FirestoreSessionService = Depends(get_session_service),
    user_id: str = Depends(get_current_user_id),
) -> Response:
    """Delete one bullet from an experience (CQ-3).

    The store could replace a bullet and append one, but never remove one — edit-only is
    half a tool, and it matters more now that a résumé re-upload can merge in lines the
    user does not want. Idempotent: an unknown entry or bullet is a no-op (204). The 404
    fires only when the user has no discovery session at all.
    """
    app_name = get_settings().app_name
    result = await run_in_threadpool(
        delete_entry_bullet,
        session_service,
        app_name=app_name,
        user_id=user_id,
        entry_id=entry_id,
        bullet_id=bullet_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="No active session.")
    return Response(status_code=204)


@router.delete("/api/experience/{entry_id}", status_code=204)
async def remove_entry(
    entry_id: str,
    session_service: FirestoreSessionService = Depends(get_session_service),
    user_id: str = Depends(get_current_user_id),
) -> Response:
    """Delete an experience AND every STAR story linked to it (CQ-3).

    The cascade is deliberate: leaving the stories behind would orphan them against an
    ``entry_id`` that no longer exists — they would still count toward the portfolio
    meter and could still be selected onto a résumé under a role the user just removed.
    If the deleted entry was the grill frontier, the frontier is cleared so the next turn
    is not aimed at an experience that is gone.

    Idempotent: an unknown entry is a no-op (204). The 404 fires only when there is no
    session at all.
    """
    app_name = get_settings().app_name
    result = await run_in_threadpool(
        delete_entry,
        session_service,
        app_name=app_name,
        user_id=user_id,
        entry_id=entry_id,
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


# ── Copywriter (CQ-4) ─────────────────────────────────────────────────────────


@router.post("/api/experience/{entry_id}/copywrite")
async def copywrite(
    entry_id: str,
    session: DiscoverySession = Depends(get_discovery_session),
) -> CopyProposalsResponse:
    """Propose rewritten bullets for ONE experience (CQ-4). Nothing is persisted.

    ONE model call on the caller's own key, batched across the whole entry — a call per
    bullet would make the grill interminable (AD-18.2). The user then accepts / edits /
    rejects each proposal; only what they accept is written back (via ``/bullets/accept``),
    so **no unreviewed prose can reach a PDF**.

    Requires a BYOK key (``get_discovery_session`` → 409 without one). An unknown entry, or a
    model/parse failure, yields an EMPTY proposal list rather than an error: copywriting is an
    improvement, never a dependency, and must not be able to take the portfolio down with it.
    """
    state = await session.current_state()
    entry = next((e for e in state.work_timeline if str(e.entry_id) == entry_id), None)
    if entry is None:
        return CopyProposalsResponse(proposals=[])
    stories = [s for s in state.extracted_star_stories if s.entry_id == entry_id]

    proposals = await run_in_threadpool(
        copywrite_entry, entry, stories, client=session.model_client
    )
    return CopyProposalsResponse(
        proposals=[
            CopyProposalResponse(source_id=p.source_id, text=p.text, original=p.original)
            for p in proposals
        ]
    )


@router.post("/api/experience/{entry_id}/bullets/accept", status_code=204)
async def accept_copywritten_bullets(
    entry_id: str,
    body: AcceptBulletsRequest,
    session_service: FirestoreSessionService = Depends(get_session_service),
    user_id: str = Depends(get_current_user_id),
) -> Response:
    """Persist the rewrites the user ACCEPTED (CQ-4). No model call, no key needed.

    A rewrite of an existing bullet SUPERSEDES it — the original is removed here, resolved by
    id, so the résumé can never carry both the polished line and the one it replaced. A
    rewrite derived from a STAR story adds a bullet the entry did not have. Rejected proposals
    are simply absent from the request and the original is untouched.

    Because the accepted text is persisted, résumé export needs **no model call at all**.
    """
    from uuid import UUID

    from web.copywriter import Proposal

    bullets = []
    for a in body.accepted:
        source_bullet_id: str | None = None
        # source_id comes from the CLIENT. A malformed one must be a 422, not an unhandled
        # ValueError out of UUID() surfacing as a 500 — and, for a `story:` id, not a
        # dangling `derived_from_story_id` quietly persisted into the contract.
        if a.source_id.startswith(("bullet:", "story:")):
            raw_id = a.source_id.split(":", 1)[1]
            try:
                UUID(raw_id)
            except ValueError as exc:
                raise HTTPException(
                    status_code=422, detail=f"Malformed source_id: {a.source_id}"
                ) from exc
            if a.source_id.startswith("bullet:"):
                source_bullet_id = raw_id
        bullets.append(
            accept_proposal(
                Proposal(
                    source_id=a.source_id,
                    text=a.text,
                    original="",
                    source_bullet_id=source_bullet_id,
                )
            )
        )

    if not bullets:
        return Response(status_code=204)  # nothing accepted → nothing to do

    result = await run_in_threadpool(
        accept_bullets,
        session_service,
        app_name=get_settings().app_name,
        user_id=user_id,
        entry_id=entry_id,
        bullets=bullets,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="No active session.")
    return Response(status_code=204)


@router.post("/api/experience/{entry_id}/bullet/{bullet_id}/skip", status_code=204)
async def skip_bullet(
    entry_id: str,
    bullet_id: str,
    body: BulletSkipRequest,
    session_service: FirestoreSessionService = Depends(get_session_service),
    user_id: str = Depends(get_current_user_id),
) -> Response:
    """Mark a bullet as explicitly skipped, or un-skip it (CQ-5).

    ``skipped`` is one of the three TERMINAL coverage states (quantified / strengthened /
    skipped). It is the escape hatch: it lets the grill insist on covering every bullet the
    user supplied without being able to trap them in an endless loop over a line they never
    cared about.

    Idempotent: an unknown entry or bullet is a no-op (204). The 404 fires only when there is
    no session at all.
    """
    result = await run_in_threadpool(
        set_bullet_skipped,
        session_service,
        app_name=get_settings().app_name,
        user_id=user_id,
        entry_id=entry_id,
        bullet_id=bullet_id,
        skipped=body.skipped,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="No active session.")
    return Response(status_code=204)
