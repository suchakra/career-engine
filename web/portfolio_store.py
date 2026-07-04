"""Portfolio-mutation seam (Phase 4D/4C) — write user edits back to the session.

The web app's read path (``web/session_loader.py``) shows what the discovery loop
recorded; this is the matching **write** path for user-initiated portfolio edits:
adding a remembered experience (4D) and steering the grill onto a chosen entry
(4C). It is the ONLY place the UI mutates persisted session state — the Streamlit
layer never writes ``session.state`` ad hoc (ARCHITECTURE AD-14.2).

Mechanism (mirrors ``cli.session.patch_state``): ADK session services return a
COPY from ``get_session``, so external state changes are committed by appending an
``Event`` carrying ``EventActions(state_delta=...)`` — the same way the workflow's
own nodes persist. State lives FLAT at the top level of ``session.state`` (see
``web/session_loader.py``), so we patch flat keys (``work_timeline``,
``grill_frontier``).

Sync bridge: the ADK session API is async and the Streamlit script thread has no
running loop, so we bridge with ``asyncio.run`` (same pattern as
``session_loader``/``workspace_store``). Do NOT call these from an async context.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from google.adk.events import Event, EventActions
from google.adk.sessions import BaseSessionService

from config import CONTRACT_VERSION
from schema import CareerEngineState, Entry, EntryStatus, ExperienceType


async def _resolve_latest_session(
    session_service: BaseSessionService, *, app_name: str, user_id: str
) -> tuple[str, CareerEngineState] | None:
    """Return the (session_id, state) of the user's newest session, or None."""
    response = await session_service.list_sessions(app_name=app_name, user_id=user_id)
    sessions = list(getattr(response, "sessions", []) or [])
    if not sessions:
        return None
    latest = max(sessions, key=lambda s: s.last_update_time or 0.0)
    full = await session_service.get_session(
        app_name=app_name, user_id=user_id, session_id=latest.id
    )
    if full is None:
        return None
    state = CareerEngineState.model_validate(full.state) if full.state else CareerEngineState()
    return latest.id, state


async def _patch_latest(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    session_id: str,
    state_delta: dict[str, object],
) -> None:
    """Commit a flat state_delta onto an existing session via an appended Event."""
    session = await session_service.get_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    )
    if session is None:  # pragma: no cover - resolved immediately before
        raise ValueError(f"Session {session_id!r} vanished mid-write.")
    event = Event(author="user", actions=EventActions(state_delta=state_delta))
    await session_service.append_event(session, event)


async def _acreate_session_with_entry(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    reference_date: str,
    entry: Entry,
) -> str:
    """Create a fresh session seeded with a single entry; return its session_id."""
    session_id = uuid4().hex
    state = CareerEngineState(reference_date=reference_date, work_timeline=[entry])
    await session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
        state=state.model_dump(mode="json"),
    )
    return session_id


async def _aadd_manual_entry(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    reference_date: str,
    entry: Entry,
) -> str:
    """Append a manual entry to the latest session (creating one if none)."""
    resolved = await _resolve_latest_session(
        session_service, app_name=app_name, user_id=user_id
    )
    if resolved is None:
        return await _acreate_session_with_entry(
            session_service,
            app_name=app_name,
            user_id=user_id,
            reference_date=reference_date,
            entry=entry,
        )
    session_id, state = resolved
    new_timeline = [*state.work_timeline, entry]
    await _patch_latest(
        session_service,
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
        state_delta={
            "work_timeline": [e.model_dump(mode="json") for e in new_timeline],
            "contract_version": CONTRACT_VERSION,
        },
    )
    return session_id


async def _aset_grill_frontier(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    entry_id: str,
) -> str | None:
    """Pin grill_frontier to entry_id on the latest session; None if no session."""
    resolved = await _resolve_latest_session(
        session_service, app_name=app_name, user_id=user_id
    )
    if resolved is None:
        return None
    session_id, _state = resolved
    await _patch_latest(
        session_service,
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
        state_delta={"grill_frontier": entry_id},
    )
    return session_id


def add_manual_entry(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    reference_date: str,
    title: str,
    org: str = "",
    experience_type: ExperienceType = ExperienceType.PROJECT,
    start_date: str = "",
    end_date: str = "",
    bullets: list[str] | None = None,
) -> str:
    """Add a user-remembered experience to the timeline (sync bridge).

    The entry is stamped ``source="manual"`` and ``status=NEEDS_QUANTIFYING`` so it
    shows in the Portfolio tree and is immediately grillable. Returns the session_id
    it was written to (an existing session, or a freshly created one).

    Raises:
        ValueError: if ``title`` is empty (an experience needs a title).
    """
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("An experience needs a title.")
    entry = Entry(
        type=experience_type,
        title=clean_title,
        org=org.strip(),
        start_date=start_date.strip(),
        end_date=end_date.strip(),
        source="manual",
        bullets=[b for b in (bullets or []) if b.strip()],
        status=EntryStatus.NEEDS_QUANTIFYING,
    )
    return asyncio.run(
        _aadd_manual_entry(
            session_service,
            app_name=app_name,
            user_id=user_id,
            reference_date=reference_date,
            entry=entry,
        )
    )


def set_grill_frontier(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    entry_id: str,
) -> str | None:
    """Pin the grill onto a chosen entry for the next turn (sync bridge).

    Sets ``grill_frontier`` (documented jumpable; honored by the router) on the
    user's latest session. Returns the session_id, or ``None`` if the user has no
    session yet (nothing to steer — the caller starts a fresh grill instead).
    """
    return asyncio.run(
        _aset_grill_frontier(
            session_service, app_name=app_name, user_id=user_id, entry_id=entry_id
        )
    )


__all__ = ["add_manual_entry", "set_grill_frontier"]
