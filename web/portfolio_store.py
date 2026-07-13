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
from schema import Bullet, BulletSource, CareerEngineState, Entry, EntryStatus, ExperienceType
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


async def aadd_manual_entry(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    reference_date: str,
    entry: Entry,
) -> str:
    """Public async wrapper over :func:`_aadd_manual_entry` (no behavior change).

    The native-async twin of :func:`add_manual_entry` for callers already inside
    an event loop (e.g. an async FastAPI endpoint), which MUST NOT use the
    :func:`web.async_runner.run_async` sync bridge. It simply awaits the existing
    private async core — no logic is duplicated or altered — and returns the
    session_id the entry was written to.
    """
    return await _aadd_manual_entry(
        session_service,
        app_name=app_name,
        user_id=user_id,
        reference_date=reference_date,
        entry=entry,
    )


async def _aset_grill_frontier(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    entry_id: str,
) -> str | None:
    """Pin grill_frontier to entry_id on the canonical session; None if no session.

    Also CLEARS ``current_question``. The frontier only takes effect on the next turn, so
    leaving the previous question persisted meant "Grill me about this" pinned entry B
    and then re-asked the user the pending question about entry A — the feature looked
    broken. An empty ``current_question`` is the client's signal to run a fresh turn,
    which the router then aims at the pinned entry.
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
    await _patch_session(
        session_service,
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
        state_delta={"grill_frontier": entry_id, "current_question": ""},
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


async def _aadd_entry_bullet(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    entry_id: str,
    text: str,
) -> str | None:
    """Append a new bullet to an entry on the canonical session.

    The twin of :func:`_aupdate_entry_bullet` (which only REPLACES an existing bullet):
    lets the user add a line to an experience they already have, without re-grilling it.
    An empty/whitespace-only ``text`` is a no-op so we never persist a blank bullet, and
    a missing entry logs a warning rather than raising. Returns the session_id, or
    ``None`` if the user has no session.
    """
    clean_text = text.strip()
    if not clean_text:
        logger.warning("add_entry_bullet: empty bullet for entry %s ignored", entry_id)
        return web_session_id(user_id)  # no-op: refuse to persist a blank bullet
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
            new_bullet = Bullet(text=clean_text, source=BulletSource.USER)
            entry = entry.model_copy(update={"bullets": [*entry.bullets, new_bullet]})
            found = True
        new_timeline.append(entry)
    if not found:
        logger.warning("add_entry_bullet: entry %s not found", entry_id)
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


async def _aupdate_entry_bullet(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    entry_id: str,
    bullet_id: str,
    new_text: str,
) -> str | None:
    """Replace one bullet on an entry with ``new_text`` on the canonical session.

    Guards against a missing entry or an unknown ``bullet_id`` (logs a
    warning and leaves state untouched). An empty or whitespace-only ``new_text`` is
    treated as a no-op so we never persist a blank bullet (matching
    :func:`add_manual_entry`, which filters empties). Returns the session_id, or ``None``
    if the user has no session.

    Addressed by ``bullet_id``, not by array index (v2.9.0, AD-18.3): an index shifts
    under any concurrent insert or delete, so a slow client could edit the wrong line.
    """
    clean_text = new_text.strip()
    if not clean_text:
        logger.warning(
            "update_entry_bullet: empty edit for entry %s bullet %s ignored",
            entry_id,
            bullet_id,
        )
        return web_session_id(user_id)  # no-op: refuse to persist a blank bullet
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
            updated_bullets = list(entry.bullets)
            match = next(
                (i for i, b in enumerate(updated_bullets) if str(b.bullet_id) == bullet_id),
                None,
            )
            if match is None:
                logger.warning(
                    "update_entry_bullet: bullet %s not found on entry %s",
                    bullet_id,
                    entry_id,
                )
                return session_id  # no-op: no such bullet
            # Edit in place: the bullet keeps its id (so anything that supersedes it, or
            # is superseded by it, stays linked) but is now the user's own wording.
            updated_bullets[match] = updated_bullets[match].model_copy(
                update={"text": clean_text, "source": BulletSource.USER}
            )
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
        bullets=[
            Bullet(text=b.strip(), source=BulletSource.USER)
            for b in (bullets or [])
            if b.strip()
        ],
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


def add_entry_bullet(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    entry_id: str,
    text: str,
) -> str | None:
    """Append a new bullet to an experience (sync bridge).

    The twin of :func:`update_entry_bullet`, which can only replace an existing one. An
    empty/whitespace-only ``text`` or a missing entry is a logged no-op (never raises).
    Returns the session_id, or ``None`` if the user has no session.
    """
    return run_async(
        _aadd_entry_bullet(
            session_service,
            app_name=app_name,
            user_id=user_id,
            entry_id=entry_id,
            text=text,
        )
    )


def update_entry_bullet(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    entry_id: str,
    bullet_id: str,
    new_text: str,
) -> str | None:
    """Edit one existing bullet on an experience in place (9A; sync bridge).

    Replaces the bullet identified by ``bullet_id`` with ``new_text`` (stripped). A
    missing entry or an unknown ``bullet_id`` is a logged no-op (never raises). Returns
    the session_id, or ``None`` if the user has no session.
    """
    return run_async(
        _aupdate_entry_bullet(
            session_service,
            app_name=app_name,
            user_id=user_id,
            entry_id=entry_id,
            bullet_id=bullet_id,
            new_text=new_text,
        )
    )


__all__ = [
    "aadd_manual_entry",
    "add_manual_entry",
    "delete_star_story",
    "set_entry_highlight",
    "set_grill_frontier",
    "update_entry_bullet",
]

# ── Résumé re-upload: MERGE, never clobber (CQ-2) ─────────────────────────────


def _norm(text: str) -> str:
    """Normalise a title/org/bullet for matching: case- and whitespace-insensitive."""
    return " ".join(text.split()).casefold()


def _entry_key(entry: Entry) -> tuple[str, str]:
    """The identity of a role for re-upload matching: its (title, org).

    Deliberately NOT including the dates. A user re-uploading an updated résumé very
    often has the same role with a corrected or extended end date ("2017-09 to present"
    vs "2017-09 to 2026-01"); keying on dates would treat that as a brand-new role and
    duplicate it, stranding the STAR stories on the old copy. Two genuinely different
    stints with the same title at the same org are rare, and merging them is a far less
    damaging error than orphaning a user's grilled work.
    """
    return (_norm(entry.title), _norm(entry.org))


def merge_work_timeline(
    existing: list[Entry], parsed: list[Entry]
) -> tuple[list[Entry], list[Entry]]:
    """Merge freshly-parsed résumé entries INTO an existing timeline. Never destroys.

    Returns ``(merged_timeline, newly_added)``.

    Before this, a second résumé upload called ``session.create``, which is
    last-write-wins: the whole ``CareerEngineState`` — every entry, every STAR story,
    every hour of grilling — was silently destroyed. Users legitimately keep several
    overlapping résumés, so a re-upload has to be additive.

    Rules:
    - A parsed entry matching an existing one (same normalised title + org) KEEPS the
      existing entry: its ``entry_id`` (so its STAR stories stay linked), its ``status``
      (a GRILLED role is not demoted back to ungrilled), and its ``highlighted`` pin.
      Only its bullets are unioned — new lines from the résumé are appended, lines it
      already has are not duplicated.
    - A parsed entry matching nothing is APPENDED as a new, ungrilled entry.
    - An existing entry the new résumé omits is KEPT. A résumé is a curated subset of a
      career, not a delete list — dropping a role because this particular résumé left it
      out would destroy grilled work the user never asked to remove.
    """
    by_key: dict[tuple[str, str], int] = {
        _entry_key(e): i for i, e in enumerate(existing)
    }
    merged = list(existing)
    added: list[Entry] = []

    for candidate in parsed:
        idx = by_key.get(_entry_key(candidate))
        if idx is None:
            merged.append(candidate)
            added.append(candidate)
            by_key[_entry_key(candidate)] = len(merged) - 1
            continue
        current = merged[idx]
        seen = {_norm(b.text) for b in current.bullets}
        fresh: list[Bullet] = []
        for b in candidate.bullets:
            key = _norm(b.text)
            # `seen` must grow as we go: a noisy parse can emit the SAME line twice within
            # one résumé, and checking only against the existing entry would let both
            # copies through.
            if not b.text.strip() or key in seen:
                continue
            seen.add(key)
            fresh.append(b)
        if fresh:
            merged[idx] = current.model_copy(
                update={"bullets": [*current.bullets, *fresh]}
            )
    return merged, added


async def _amerge_parsed_entries(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    entries: list[Entry],
) -> str | None:
    """Merge parsed résumé entries into the caller's EXISTING session (never create).

    Returns the session_id, or ``None`` if the user has no session (the caller should
    then create one — a first upload has nothing to merge into).

    Also aims the grill at the newly-added roles: the frontier moves to the first new
    entry and ``current_question`` is cleared, so the next turn asks about work we have
    not grilled yet rather than re-asking a pending question about an old one.
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

    merged, added = merge_work_timeline(existing.work_timeline, entries)
    delta: dict[str, object] = {
        "work_timeline": [e.model_dump(mode="json") for e in merged],
        "contract_version": CONTRACT_VERSION,
    }
    if added:
        delta["grill_frontier"] = str(added[0].entry_id)
        delta["current_question"] = ""
    await _patch_session(
        session_service,
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
        state_delta=delta,
    )
    logger.info(
        "amerge_parsed_entries: %d parsed -> %d added, %d total (no entry or story removed)",
        len(entries),
        len(added),
        len(merged),
    )
    return session_id


async def amerge_parsed_entries(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    entries: list[Entry],
) -> str | None:
    """Public async wrapper over :func:`_amerge_parsed_entries` (for async callers)."""
    return await _amerge_parsed_entries(
        session_service, app_name=app_name, user_id=user_id, entries=entries
    )

# ── Delete (CQ-3): the store could replace and append a bullet, never remove one ──


async def _adelete_entry_bullet(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    entry_id: str,
    bullet_id: str,
) -> str | None:
    """Remove one bullet from an entry, addressed by its ``bullet_id``.

    Idempotent: an unknown entry or bullet is a logged no-op. Returns the session_id, or
    ``None`` if the user has no session.
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
            remaining = [b for b in entry.bullets if str(b.bullet_id) != bullet_id]
            if len(remaining) == len(entry.bullets):
                logger.warning(
                    "delete_entry_bullet: bullet %s not found on entry %s", bullet_id, entry_id
                )
                return session_id  # no-op: no such bullet
            entry = entry.model_copy(update={"bullets": remaining})
            found = True
        new_timeline.append(entry)
    if not found:
        logger.warning("delete_entry_bullet: entry %s not found", entry_id)
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


async def _adelete_entry(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    entry_id: str,
) -> str | None:
    """Remove an experience AND every STAR story linked to it.

    Deleting the entry without its stories would leave them pointing at an ``entry_id``
    that no longer exists — orphans that still count toward the portfolio meter and can
    still be selected onto a résumé under a role the user just removed. So the delete is
    a cascade, and it is the ONLY place in the store that removes a STAR story as a side
    effect. If the deleted entry was the grill frontier, the frontier is cleared too, so
    the next turn is not aimed at an experience that is gone.

    Idempotent: an unknown entry is a logged no-op. Returns the session_id, or ``None``
    if the user has no session.
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
    remaining = [e for e in existing.work_timeline if str(e.entry_id) != entry_id]
    if len(remaining) == len(existing.work_timeline):
        logger.warning("delete_entry: entry %s not found", entry_id)
        return session_id  # no-op: entry not found

    kept_stories = [s for s in existing.extracted_star_stories if s.entry_id != entry_id]
    dropped = len(existing.extracted_star_stories) - len(kept_stories)
    delta: dict[str, object] = {
        "work_timeline": [e.model_dump(mode="json") for e in remaining],
        "extracted_star_stories": [s.model_dump(mode="json") for s in kept_stories],
        # Per-entry grill buffers are keyed by entry_id, so they must be pruned with the
        # entry or they linger forever against an id that no longer exists.
        "grill_attempts": {
            k: v for k, v in existing.grill_attempts.items() if k != entry_id
        },
        "grill_answers": {
            k: v for k, v in existing.grill_answers.items() if k != entry_id
        },
        "contract_version": CONTRACT_VERSION,
    }
    if existing.grill_frontier == entry_id:
        delta["grill_frontier"] = ""
        delta["current_question"] = ""
        # CRITICAL: a pending answer was typed about the entry we are deleting. Left in
        # place, the next turn would consume it as the answer to whatever entry becomes
        # the new frontier — attaching a story to the WRONG role.
        delta["pending_user_answer"] = ""
    await _patch_session(
        session_service,
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
        state_delta=delta,
    )
    logger.info("delete_entry: removed entry %s and %d orphaned story/ies", entry_id, dropped)
    return session_id


def delete_entry_bullet(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    entry_id: str,
    bullet_id: str,
) -> str | None:
    """Remove one bullet from an experience (sync bridge). Idempotent."""
    return run_async(
        _adelete_entry_bullet(
            session_service,
            app_name=app_name,
            user_id=user_id,
            entry_id=entry_id,
            bullet_id=bullet_id,
        )
    )


def delete_entry(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    entry_id: str,
) -> str | None:
    """Remove an experience and its STAR stories (sync bridge). Idempotent."""
    return run_async(
        _adelete_entry(
            session_service, app_name=app_name, user_id=user_id, entry_id=entry_id
        )
    )


async def _aaccept_bullets(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    entry_id: str,
    bullets: list[Bullet],
) -> str | None:
    """Persist copywriter bullets the user ACCEPTED (CQ-4).

    Each accepted bullet is appended with ``source="grilled"``. When it ``supersedes`` one of
    the entry's existing bullets, that original is REMOVED here — resolved by id, so the
    résumé can never show both the polished line and the original it replaced. (The
    alternative, leaving both and de-duplicating at render time by text similarity, is exactly
    the guessing game that AD-18.3 exists to end.)

    Idempotent-ish: an unknown entry is a logged no-op. Returns the session_id, or ``None`` if
    the user has no session.
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

    # Normalise provenance HERE rather than trusting every caller to remember: anything
    # persisted through this seam is, by definition, a copywriter bullet the user accepted.
    bullets = [b.model_copy(update={"source": BulletSource.GRILLED}) for b in bullets]
    superseded = {str(b.supersedes) for b in bullets if b.supersedes is not None}
    found = False
    new_timeline: list[Entry] = []
    for entry in existing.work_timeline:
        if str(entry.entry_id) == entry_id:
            kept = [b for b in entry.bullets if str(b.bullet_id) not in superseded]
            entry = entry.model_copy(update={"bullets": [*kept, *bullets]})
            found = True
        new_timeline.append(entry)
    if not found:
        logger.warning("accept_bullets: entry %s not found", entry_id)
        return session_id
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
    logger.info(
        "accept_bullets: entry %s gained %d bullet(s), superseding %d",
        entry_id,
        len(bullets),
        len(superseded),
    )
    return session_id


def accept_bullets(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    entry_id: str,
    bullets: list[Bullet],
) -> str | None:
    """Sync bridge over :func:`_aaccept_bullets`."""
    return run_async(
        _aaccept_bullets(
            session_service,
            app_name=app_name,
            user_id=user_id,
            entry_id=entry_id,
            bullets=bullets,
        )
    )


async def _aset_bullet_skipped(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    entry_id: str,
    bullet_id: str,
    skipped: bool,
) -> str | None:
    """Mark a bullet as explicitly skipped, or un-skip it (CQ-5).

    ``skipped`` is one of the three TERMINAL coverage states, and it is the escape hatch that
    lets the grill insist on covering every supplied bullet without being able to trap the
    user in an endless loop over a line they never cared about.

    Idempotent: an unknown entry or bullet is a logged no-op. Returns the session_id, or
    ``None`` if the user has no session.
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
            # Detect "not found" by ID, not by comparing the resulting lists: skipping an
            # ALREADY-skipped bullet is a legitimate idempotent replay that produces an
            # identical list, and the old comparison logged it as "bullet not found" — poisoning
            # the very signal used to debug a real id mismatch.
            if not any(str(b.bullet_id) == bullet_id for b in entry.bullets):
                logger.warning(
                    "set_bullet_skipped: bullet %s not found on entry %s", bullet_id, entry_id
                )
                return session_id
            updated = [
                b.model_copy(update={"skipped": skipped})
                if str(b.bullet_id) == bullet_id
                else b
                for b in entry.bullets
            ]
            entry = entry.model_copy(update={"bullets": updated})
            found = True
        new_timeline.append(entry)
    if not found:
        logger.warning("set_bullet_skipped: entry %s not found", entry_id)
        return session_id
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


def set_bullet_skipped(
    session_service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    entry_id: str,
    bullet_id: str,
    skipped: bool,
) -> str | None:
    """Sync bridge over :func:`_aset_bullet_skipped`."""
    return run_async(
        _aset_bullet_skipped(
            session_service,
            app_name=app_name,
            user_id=user_id,
            entry_id=entry_id,
            bullet_id=bullet_id,
            skipped=skipped,
        )
    )
