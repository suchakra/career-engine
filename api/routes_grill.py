"""Protected streaming grill routes for the API (Phase 10.4, AD-16.5).

Exposes the interactive "grill" (the ``DiscoverySession`` turn loop) over HTTP with
**no graph changes** — pure presentation/transport that reuses ``cli.app`` and
``workflows.nodes``. Two endpoints implement the AD-16.5 "record then stream" shape:

- ``POST /api/grill`` — **records** the caller's input into the durable canonical
  session (``web-{user_id}``) and does NOT run the graph. The answer travels in the
  request BODY, never a URL query string, so grill PII never lands in access logs.
- ``GET /api/grill/stream`` — Server-Sent Events (``text/event-stream``). **Runs** the
  pending turn sequence by looping :meth:`DiscoverySession.advance` and emits one
  ``event: turn`` per completed turn, then a terminal ``event: done``. A mid-stream
  :class:`ModelAPIError` is caught and surfaced as a final ``event: error`` frame
  (never a 500 mid-flight).

Auth: both endpoints reuse :func:`api.deps.get_current_user_id` (401 without a token)
AND :func:`api.deps.get_discovery_session` (builds the BYOK session; 409 if no key).
The explicit ``get_current_user_id`` dependency guarantees 401 even in tests, which
override ``get_discovery_session`` wholesale with a scripted, network-free session.

Async discipline (mirrors 10.2/10.3): endpoints + the SSE generator are ``async`` and
await :class:`DiscoverySession` directly. No ``streamlit``, no ``web.async_runner``,
no ``asyncio.run`` under ``api/``.
"""

from __future__ import annotations

import pathlib
from collections.abc import AsyncIterator
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from api.deps import get_current_user_id, get_discovery_session
from api.schemas import (
    GrillActionRequest,
    GrillErrorEvent,
    GrillSnapshot,
    GrillTurnEvent,
)
from cli.app import DiscoverySession, TurnResult, guess_resume_mime
from integration.model_client import ModelAPIError
from schema import CareerEngineState, PhaseStatus
from tools.resume_parser import ParseError, parse_resume
from web.grill_labels import _effective_frontier_label

router = APIRouter()

_MAX_AUTO_TURNS = 6  # bound the non-interactive drive to finalize (mirrors web/grill_ui)


def _awaiting(state: CareerEngineState) -> Literal["question", "checkpoint", "complete"]:
    """Map the session phase onto what the client should render next."""
    if state.current_phase == PhaseStatus.COMPLETE:
        return "complete"
    if state.current_phase == PhaseStatus.CHECKPOINT:
        return "checkpoint"
    return "question"


def _sse_frame(event: str, payload: BaseModel) -> str:
    """Serialise a strict DTO into one SSE frame (``event:`` + ``data:`` + blank line)."""
    return f"event: {event}\ndata: {payload.model_dump_json()}\n\n"


def _turn_event(turn: TurnResult, state: CareerEngineState) -> GrillTurnEvent:
    """Build the strict per-turn SSE payload from a ``TurnResult`` + post-turn state."""
    return GrillTurnEvent(
        next_question=turn.next_question,
        checkpoint_summary=turn.checkpoint_summary,
        is_complete=turn.is_complete,
        upgrade_required=turn.upgrade_required,
        upgrade_message=turn.upgrade_message,
        stories_count=turn.stories_count,
        phase=turn.phase.value,
        frontier_label=_effective_frontier_label(state),
    )


@router.post("/api/grill")
async def record_grill_action(
    body: GrillActionRequest,
    user_id: str = Depends(get_current_user_id),
    session: DiscoverySession = Depends(get_discovery_session),
) -> GrillSnapshot:
    """Record the caller's grill input into the durable session WITHOUT running the graph.

    Requires a valid bearer token. Dispatches on ``body.action``:
    ``start`` creates the session from ``history`` (with an injected ``reference_date``
    default of today), ``answer`` records ``pending_user_answer``, ``confirm`` records
    ``checkpoint_verified``. Returns a small status snapshot read AFTER the record so
    the client can render the banner + await state before opening the SSE stream. A
    malformed body / bad ``action`` yields 422 automatically. ``start`` with an
    empty ``history`` and ``answer`` with an empty ``answer`` are also rejected with
    422 (recording a turn with no user input is a client error, not a valid state).
    """
    if body.action == "start":
        if not body.history.strip():
            raise HTTPException(status_code=422, detail="history is required for 'start'")
        await session.create(
            body.history,
            reference_date=body.reference_date or date.today().isoformat(),
        )
    elif body.action == "answer":
        if not body.answer.strip():
            raise HTTPException(status_code=422, detail="answer is required for 'answer'")
        await session.record_answer(body.answer)
    else:  # "confirm" — the only remaining Literal value
        await session.record_checkpoint_confirmation()
    state = await session.current_state()
    return GrillSnapshot(
        phase=state.current_phase.value,
        frontier_label=_effective_frontier_label(state),
        awaiting=_awaiting(state),
    )


@router.post("/api/grill/resume")
async def seed_from_resume(
    file: UploadFile = File(...),
    session: DiscoverySession = Depends(get_discovery_session),
) -> GrillSnapshot:
    """Vision-parse an uploaded résumé into a starting timeline and seed the grill.

    Requires a valid bearer token AND a BYOK key (``get_discovery_session`` → 409). The
    file (PDF/PNG/JPG/WEBP) is parsed by the multimodal model on the user's OWN key
    (``tools.resume_parser.parse_resume``) into ``Entry`` objects — the raw bytes are
    never stored — and used to ``create`` the durable session (``work_timeline``). Returns
    the post-record snapshot so the client can open the SSE stream, exactly like ``start``.
    """
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="Empty résumé file.")
    mime = file.content_type or guess_resume_mime(pathlib.Path(file.filename or ""))
    try:
        entries = await run_in_threadpool(
            parse_resume, data, mime, client=session.model_client
        )
    except ParseError as exc:
        raise HTTPException(status_code=422, detail=f"Couldn't parse résumé: {exc}") from exc
    await session.create(
        "", reference_date=date.today().isoformat(), work_timeline=entries
    )
    state = await session.current_state()
    return GrillSnapshot(
        phase=state.current_phase.value,
        frontier_label=_effective_frontier_label(state),
        awaiting=_awaiting(state),
    )


@router.get("/api/grill/stream")
async def stream_grill_turns(
    user_id: str = Depends(get_current_user_id),
    session: DiscoverySession = Depends(get_discovery_session),
) -> StreamingResponse:
    """Run the pending turn sequence and stream one ``event: turn`` per completed turn.

    Requires a valid bearer token. The async generator runs the first (pre-recorded)
    turn, then auto-advances — but ONLY after a story is accepted — bounded by
    ``_MAX_AUTO_TURNS``, stopping on next-question / checkpoint / complete / upgrade
    (mirrors ``web/grill_ui._submit_answer`` exactly). Each completed turn is emitted
    as an ``event: turn`` frame; a terminal ``event: done`` carries the final turn. A
    :class:`ModelAPIError` mid-stream is caught and emitted as ``event: error`` instead
    of 500-ing the response.
    """

    async def _generate() -> AsyncIterator[str]:
        try:
            before = await session.current_state()
            turn = await session.advance()  # answer was pre-recorded by POST
            # Read state ONCE per completed turn and reuse it for the event, the
            # accept check, and (below) the terminal frame — a Firestore-backed
            # session makes each ``current_state()`` a network read.
            state = await session.current_state()
            yield _sse_frame("turn", _turn_event(turn, state))
            accepted = len(state.extracted_star_stories) > len(
                before.extracted_star_stories
            )
            if accepted:
                for _ in range(_MAX_AUTO_TURNS):
                    if (
                        turn.upgrade_required
                        or turn.is_complete
                        or turn.checkpoint_summary
                        or turn.next_question
                    ):
                        break
                    turn = await session.advance()
                    state = await session.current_state()
                    yield _sse_frame("turn", _turn_event(turn, state))
            # ``state`` already reflects the final turn — no extra read needed.
            yield _sse_frame("done", _turn_event(turn, state))
        except ModelAPIError as exc:
            error = GrillErrorEvent(
                message=str(exc), rate_limited=exc.is_rate_limited
            )
            yield _sse_frame("error", error)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
