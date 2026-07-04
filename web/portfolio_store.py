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
running loop, so we bridge with :func:`web.async_runner.run_async` (a shared
persistent loop — see that module for why ``asyncio.run`` per call breaks reused
async clients). Do NOT call these from an async context.
"""

from __future__ import annotations

from google.adk.events import Event, EventActions
from google.adk.sessions import BaseSessionService

from cli import session as session_helpers
from config import CONTRACT_VERSION
from schema import CareerEngineState, Entry, EntryStatus, ExperienceType
from web.async_runner import run_async
from web.session_loader import web_session_id


async def _patch_session(
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


async def _aadd_manual_entry(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    reference_date: str,
    entry: Entry,
) -> str:
    """Append a manual entry to the user's canonical session (creating it if none).

    Targets the SAME stable session the grill + Portfolio view use, so a manually
    added experience shows in the tree and is immediately grillable.
    """
    session_id = web_session_id(user_id)
    existing = await session_helpers.get_session_state_if_exists(
        session_service=session_service,
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )
    if existing is None:
        state = CareerEngineState(reference_date=reference_date, work_timeline=[entry])
        await session_service.create_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
            state=state.model_dump(mode="json"),
        )
        return session_id
    new_timeline = [*existing.work_timeline, entry]
    await _patch_session(
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
    """Pin grill_frontier to entry_id on the canonical session; None if no session."""
    session_id = web_session_id(user_id)
    existing = await session_helpers.get_session_state_if_exists(
        session_service=session_service,
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )
    if existing is None:
        return None
    await _patch_session(
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
    return run_async(
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
    return run_async(
        _aset_grill_frontier(
            session_service, app_name=app_name, user_id=user_id, entry_id=entry_id
        )
    )


__all__ = ["add_manual_entry", "set_grill_frontier"]
