"""Load a user's latest discovery-session state for the web progress meter (2A).

The dashboard's progress meter reflects how far a user got in the "Grill Me"
discovery graph. Discovery state lives in the ADK session service (keyed by
``app_name / user_id / session_id``), separate from the ``UserWorkspace`` doc.
This module resolves the user's most-recently-updated session and returns its
``CareerEngineState`` — best-effort, read-only, and never fatal to the UI.

Sync bridge: ``list_sessions`` / ``get_session`` are async on
``BaseSessionService``; the Streamlit script thread has no running event loop, so
we bridge with :func:`web.async_runner.run_async` (a shared persistent loop —
NOT ``asyncio.run`` per call, which would close the loop a reused async Firestore
client's gRPC channel is bound to → "Event loop is closed").
Do NOT call these from an async context.
"""

from __future__ import annotations

import logging

from google.adk.sessions import BaseSessionService

from schema import CareerEngineState
from web.async_runner import run_async

_log = logging.getLogger("career_engine.web")


def web_session_id(user_id: str) -> str:
    """The canonical, stable discovery-session id for a web user (one per user).

    Deterministic so the grill (write path), the Portfolio view (read path), and
    the add-experience seam all address the SAME durable session — the user keeps
    building one resumable portfolio instead of spawning orphaned sessions.
    """
    return f"web-{user_id}"


async def _aload_latest_discovery_state(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    reference_date: str,
) -> CareerEngineState:
    """Async core: read the user's most-recent session state, or an empty state."""
    empty = CareerEngineState(reference_date=reference_date)

    # Prefer the canonical per-user session — the exact one the web grill + the
    # add-experience seam write — so the read (meter / Portfolio) can never diverge
    # from the write path. Fall back to the most-recent session only if the
    # canonical one doesn't exist (e.g. legacy/other sessions).
    full = await session_service.get_session(
        app_name=app_name, user_id=user_id, session_id=web_session_id(user_id)
    )
    if full is None:
        response = await session_service.list_sessions(app_name=app_name, user_id=user_id)
        sessions = list(getattr(response, "sessions", []) or [])
        if not sessions:
            return empty
        # list_sessions may return lightweight sessions (no state); fetch the newest
        # by last_update_time and read its full state.
        latest = max(sessions, key=lambda s: s.last_update_time or 0.0)
        full = await session_service.get_session(
            app_name=app_name, user_id=user_id, session_id=latest.id
        )
    if full is None or not full.state:
        return empty
    # CareerEngineState fields live FLAT at the top level of session.state (see
    # discovery_graph._write_state and cli.session.read_state). Validate the whole
    # state dict — do NOT reach into a nested "career_engine_state" key: after a
    # FirestoreSessionService round-trip that sub-key holds an EMPTY default while
    # the real fields remain flat at the top level.
    loaded = CareerEngineState.model_validate(full.state)
    # The meter is a "today" view: recompute completeness relative to the injected
    # date, not the (possibly stale or empty) date persisted with the session.
    return loaded.model_copy(update={"reference_date": reference_date})


def load_latest_discovery_state(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    reference_date: str,
) -> CareerEngineState:
    """Return the user's most-recent discovery ``CareerEngineState`` (sync bridge).

    Raises on a genuine backend error; use :func:`try_load_latest_discovery_state`
    for the non-fatal UX path.
    """
    return run_async(
        _aload_latest_discovery_state(
            session_service,
            app_name=app_name,
            user_id=user_id,
            reference_date=reference_date,
        )
    )


def try_load_latest_discovery_state(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    reference_date: str,
) -> CareerEngineState:
    """Best-effort loader for the UI: returns an empty state on ANY failure.

    A missing session, an unreachable/uncredentialed backend, or an
    incompatible-contract document must never crash the dashboard — the meter
    simply shows no progress. The failure is logged generically (no PII, no
    stack) so ops can distinguish "no session yet" from a backend fault.
    """
    try:
        return load_latest_discovery_state(
            session_service,
            app_name=app_name,
            user_id=user_id,
            reference_date=reference_date,
        )
    except Exception:
        _log.warning("could not load discovery state for the meter; showing empty progress")
        return CareerEngineState(reference_date=reference_date)
