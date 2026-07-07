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

import logging

from google.adk.events import Event, EventActions
from google.adk.sessions import BaseSessionService

from cli import session as session_helpers
from config import CONTRACT_VERSION
from schema import CareerEngineState, Entry, EntryStatus, ExperienceType
from web.async_runner import run_async
from web.session_loader import web_session_id

logger = logging.getLogger(__name__)


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


async def _aset_entry_highlight(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    entry_id: str,
    highlighted: bool,
) -> str | None:
    """Flip an entry's ``highlighted`` flag on the canonical session; None if absent."""
    session_id = web_session_id(user_id)
    existing = await session_helpers.get_session_state_if_exists(
        session_service=session_service,
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )
    if existing is None:
        return None
    found = False
    new_timeline: list[Entry] = []
    for entry in existing.work_timeline:
        if str(entry.entry_id) == entry_id:
            entry = entry.model_copy(update={"highlighted": highlighted})
            found = True
        new_timeline.append(entry)
    if not found:
        return None
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


async def _adelete_star_story(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    story_id: str,
) -> str | None:
    """Remove the STAR story whose ``story_id`` matches from the canonical session.

    Idempotent: if no story matches (or the session is empty of it), the state is
    left untouched. Returns the session_id, or ``None`` if the user has no session.
    """
    session_id = web_session_id(user_id)
    existing = await session_helpers.get_session_state_if_exists(
        session_service=session_service,
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )
    if existing is None:
        return None
    remaining = [s for s in existing.extracted_star_stories if str(s.story_id) != story_id]
    if len(remaining) == len(existing.extracted_star_stories):
        return session_id  # no-op: story_id not found
    await _patch_session(
        session_service,
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
        state_delta={
            "extracted_star_stories": [s.model_dump(mode="json") for s in remaining],
            "contract_version": CONTRACT_VERSION,
        },
    )
    return session_id


async def _aupdate_entry_bullet(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    entry_id: str,
    bullet_index: int,
    new_text: str,
) -> str | None:
    """Replace one bullet on an entry with ``new_text`` on the canonical session.

    Guards against a missing entry or an out-of-range ``bullet_index`` (logs a
    warning and leaves state untouched — no ``IndexError``). Returns the
    session_id, or ``None`` if the user has no session.
    """
    session_id = web_session_id(user_id)
    existing = await session_helpers.get_session_state_if_exists(
        session_service=session_service,
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )
    if existing is None:
        return None
    found = False
    new_timeline: list[Entry] = []
    for entry in existing.work_timeline:
        if str(entry.entry_id) == entry_id:
            if not 0 <= bullet_index < len(entry.bullets):
                logger.warning(
                    "update_entry_bullet: bullet_index %d out of range for entry %s (has %d bullets)",
                    bullet_index,
                    entry_id,
                    len(entry.bullets),
                )
                return session_id  # no-op: out of range
            updated_bullets = list(entry.bullets)
            updated_bullets[bullet_index] = new_text.strip()
            entry = entry.model_copy(update={"bullets": updated_bullets})
            found = True
        new_timeline.append(entry)
    if not found:
        logger.warning("update_entry_bullet: entry %s not found", entry_id)
        return session_id  # no-op: entry not found
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


def set_entry_highlight(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    entry_id: str,
    highlighted: bool,
) -> str | None:
    """Pin/unpin an experience as a tailoring priority (4E; sync bridge).

    Sets ``Entry.highlighted`` on the canonical session so the Tailor always
    includes this experience's achievements. Returns the session_id, or ``None``
    if the user has no session or the entry isn't found.
    """
    return run_async(
        _aset_entry_highlight(
            session_service,
            app_name=app_name,
            user_id=user_id,
            entry_id=entry_id,
            highlighted=highlighted,
        )
    )


def delete_star_story(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    story_id: str,
) -> str | None:
    """Delete a recorded STAR story from the portfolio (9A; sync bridge).

    Removes the story whose ``story_id`` matches. Idempotent — a non-existent
    ``story_id`` is a no-op. Returns the session_id, or ``None`` if the user has no
    session.
    """
    return run_async(
        _adelete_star_story(
            session_service, app_name=app_name, user_id=user_id, story_id=story_id
        )
    )


def update_entry_bullet(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    entry_id: str,
    bullet_index: int,
    new_text: str,
) -> str | None:
    """Edit one existing bullet on an experience in place (9A; sync bridge).

    Replaces ``entry.bullets[bullet_index]`` with ``new_text`` (stripped). A missing
    entry or an out-of-range index is a logged no-op (never raises). Returns the
    session_id, or ``None`` if the user has no session.
    """
    return run_async(
        _aupdate_entry_bullet(
            session_service,
            app_name=app_name,
            user_id=user_id,
            entry_id=entry_id,
            bullet_index=bullet_index,
            new_text=new_text,
        )
    )


__all__ = [
    "add_manual_entry",
    "delete_star_story",
    "set_entry_highlight",
    "set_grill_frontier",
    "update_entry_bullet",
]
