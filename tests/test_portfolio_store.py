"""Tests for the portfolio-mutation seam (Phase 4D/4C).

Uses ADK's real ``InMemorySessionService`` so the state_delta merge semantics
match production (the seam commits via an appended Event, like the workflow's own
nodes). Covers: add-to-existing, add-when-none (creates a session), contract
stamping, title validation, and the grill_frontier jump (incl. the no-session case).
"""

from __future__ import annotations

import asyncio
from typing import cast

from google.adk.sessions import BaseSessionService, InMemorySessionService

from config import CONTRACT_VERSION
from schema import CareerEngineState, Entry, ExperienceType, StarStory
from web.portfolio_store import (
    add_entry_bullet,
    add_manual_entry,
    delete_star_story,
    set_entry_highlight,
    set_grill_frontier,
    update_entry_bullet,
)
from web.session_loader import web_session_id

_APP = "career-engine"
_UID = "user-1"
_REF = "2026-07-04"
_SID = web_session_id(_UID)  # the canonical per-user session id the seam targets


def _service() -> BaseSessionService:
    return cast(BaseSessionService, InMemorySessionService())  # type: ignore[no-untyped-call]


def _seed(service: BaseSessionService, state: CareerEngineState, *, sid: str = _SID) -> None:
    asyncio.run(
        service.create_session(
            app_name=_APP, user_id=_UID, session_id=sid, state=state.model_dump(mode="json")
        )
    )


def _read_latest(service: BaseSessionService) -> CareerEngineState:
    async def _go() -> CareerEngineState:
        response = await service.list_sessions(app_name=_APP, user_id=_UID)
        sessions = list(getattr(response, "sessions", []) or [])
        latest = max(sessions, key=lambda s: s.last_update_time or 0.0)
        full = await service.get_session(app_name=_APP, user_id=_UID, session_id=latest.id)
        assert full is not None
        return CareerEngineState.model_validate(full.state)

    return asyncio.run(_go())


class TestAddManualEntry:
    def test_appends_to_existing_session(self) -> None:
        service = _service()
        existing = Entry(type=ExperienceType.FULL_TIME, title="Staff Engineer", org="Acme")
        _seed(service, CareerEngineState(reference_date=_REF, work_timeline=[existing]))

        add_manual_entry(
            service,
            app_name=_APP,
            user_id=_UID,
            reference_date=_REF,
            title="Billing rewrite",
            org="Acme",
            experience_type=ExperienceType.PROJECT,
        )

        state = _read_latest(service)
        assert [e.title for e in state.work_timeline] == ["Staff Engineer", "Billing rewrite"]
        added = state.work_timeline[-1]
        assert added.source == "manual"
        assert added.type == ExperienceType.PROJECT

    def test_creates_session_when_none_exists(self) -> None:
        service = _service()
        sid = add_manual_entry(
            service,
            app_name=_APP,
            user_id=_UID,
            reference_date=_REF,
            title="Open-source parser",
            experience_type=ExperienceType.OPEN_SOURCE,
        )
        assert sid
        state = _read_latest(service)
        assert len(state.work_timeline) == 1
        assert state.work_timeline[0].title == "Open-source parser"
        assert state.work_timeline[0].source == "manual"

    def test_saved_state_is_contract_stamped(self) -> None:
        service = _service()
        _seed(service, CareerEngineState(reference_date=_REF))
        add_manual_entry(
            service, app_name=_APP, user_id=_UID, reference_date=_REF, title="Thing"
        )
        assert _read_latest(service).contract_version == CONTRACT_VERSION

    def test_bullets_are_cleaned(self) -> None:
        service = _service()
        add_manual_entry(
            service,
            app_name=_APP,
            user_id=_UID,
            reference_date=_REF,
            title="Thing",
            bullets=["Did X", "  ", "Did Y"],
        )
        assert _read_latest(service).work_timeline[0].bullets == ["Did X", "Did Y"]

    def test_empty_title_rejected(self) -> None:
        service = _service()
        try:
            add_manual_entry(
                service, app_name=_APP, user_id=_UID, reference_date=_REF, title="   "
            )
        except ValueError:
            return
        raise AssertionError("empty title should raise ValueError")


class TestSetGrillFrontier:
    def test_pins_frontier_on_latest_session(self) -> None:
        service = _service()
        entry = Entry(type=ExperienceType.PROJECT, title="Billing rewrite")
        _seed(service, CareerEngineState(reference_date=_REF, work_timeline=[entry]))

        sid = set_grill_frontier(
            service, app_name=_APP, user_id=_UID, entry_id=str(entry.entry_id)
        )
        assert sid is not None
        assert _read_latest(service).grill_frontier == str(entry.entry_id)

    def test_clears_the_stale_pending_question(self) -> None:
        """Pinning a NEW entry must drop the question still pending about the old one.

        Regression: the frontier only takes effect on the next turn, so leaving
        ``current_question`` in place meant "Grill me about this" pinned entry B and then
        re-asked the user the pending question about entry A. An empty
        ``current_question`` is the client's signal to run a fresh turn.
        """
        service = _service()
        entry = Entry(type=ExperienceType.PROJECT, title="Billing rewrite")
        _seed(
            service,
            CareerEngineState(
                reference_date=_REF,
                work_timeline=[entry],
                current_question="What did the OTHER entry save you?",
            ),
        )

        set_grill_frontier(
            service, app_name=_APP, user_id=_UID, entry_id=str(entry.entry_id)
        )

        state = _read_latest(service)
        assert state.grill_frontier == str(entry.entry_id)
        assert state.current_question == ""

    def test_returns_none_when_no_session(self) -> None:
        service = _service()
        result = set_grill_frontier(
            service, app_name=_APP, user_id=_UID, entry_id="whatever"
        )
        assert result is None


class TestSetEntryHighlight:
    def test_pins_entry_on_latest_session(self) -> None:
        service = _service()
        entry = Entry(type=ExperienceType.PROJECT, title="Billing rewrite")
        _seed(service, CareerEngineState(reference_date=_REF, work_timeline=[entry]))

        sid = set_entry_highlight(
            service, app_name=_APP, user_id=_UID, entry_id=str(entry.entry_id), highlighted=True
        )
        assert sid is not None
        state = _read_latest(service)
        assert state.work_timeline[0].highlighted is True
        assert state.contract_version == CONTRACT_VERSION

    def test_unpin_sets_false(self) -> None:
        service = _service()
        entry = Entry(type=ExperienceType.PROJECT, title="X", highlighted=True)
        _seed(service, CareerEngineState(reference_date=_REF, work_timeline=[entry]))

        set_entry_highlight(
            service, app_name=_APP, user_id=_UID, entry_id=str(entry.entry_id), highlighted=False
        )
        assert _read_latest(service).work_timeline[0].highlighted is False

    def test_returns_none_when_no_session(self) -> None:
        service = _service()
        assert (
            set_entry_highlight(
                service, app_name=_APP, user_id=_UID, entry_id="x", highlighted=True
            )
            is None
        )

    def test_returns_none_when_entry_not_found(self) -> None:
        service = _service()
        _seed(
            service,
            CareerEngineState(
                reference_date=_REF,
                work_timeline=[Entry(type=ExperienceType.PROJECT, title="X")],
            ),
        )
        assert (
            set_entry_highlight(
                service, app_name=_APP, user_id=_UID, entry_id="nonexistent", highlighted=True
            )
            is None
        )


class TestDeleteStarStory:
    def test_delete_star_story_removes_from_state(self) -> None:
        service = _service()
        entry = Entry(type=ExperienceType.PROJECT, title="Billing rewrite")
        story_a = StarStory(entry_id=str(entry.entry_id), pillar="delivery", result="cut latency 40%")
        story_b = StarStory(entry_id=str(entry.entry_id), pillar="delivery", result="shipped X")
        _seed(
            service,
            CareerEngineState(
                reference_date=_REF,
                work_timeline=[entry],
                extracted_star_stories=[story_a, story_b],
            ),
        )

        sid = delete_star_story(
            service, app_name=_APP, user_id=_UID, story_id=str(story_a.story_id)
        )
        assert sid is not None
        state = _read_latest(service)
        remaining = [str(s.story_id) for s in state.extracted_star_stories]
        assert remaining == [str(story_b.story_id)]

    def test_delete_star_story_idempotent(self) -> None:
        service = _service()
        story = StarStory(pillar="delivery", result="did a thing")
        _seed(
            service,
            CareerEngineState(reference_date=_REF, extracted_star_stories=[story]),
        )

        # Deleting a non-existent story is a no-op and must not raise.
        sid = delete_star_story(
            service, app_name=_APP, user_id=_UID, story_id="not-a-real-story-id"
        )
        assert sid is not None
        state = _read_latest(service)
        assert [str(s.story_id) for s in state.extracted_star_stories] == [str(story.story_id)]

    def test_returns_none_when_no_session(self) -> None:
        service = _service()
        assert (
            delete_star_story(service, app_name=_APP, user_id=_UID, story_id="anything") is None
        )


class TestAddEntryBullet:
    def test_add_entry_bullet_appends(self) -> None:
        """A new bullet lands at the END of the entry's existing bullets."""
        service = _service()
        entry = Entry(
            type=ExperienceType.PROJECT, title="Billing rewrite", bullets=["first"]
        )
        _seed(service, CareerEngineState(reference_date=_REF, work_timeline=[entry]))

        sid = add_entry_bullet(
            service,
            app_name=_APP,
            user_id=_UID,
            entry_id=str(entry.entry_id),
            text="  second  ",
        )
        assert sid is not None
        state = _read_latest(service)
        assert state.work_timeline[0].bullets == ["first", "second"]  # stripped + appended
        assert state.contract_version == CONTRACT_VERSION

    def test_add_entry_bullet_refuses_a_blank(self) -> None:
        """A whitespace-only bullet is a no-op — never persist an empty line."""
        service = _service()
        entry = Entry(type=ExperienceType.PROJECT, title="Billing", bullets=["first"])
        _seed(service, CareerEngineState(reference_date=_REF, work_timeline=[entry]))

        add_entry_bullet(
            service, app_name=_APP, user_id=_UID, entry_id=str(entry.entry_id), text="   "
        )
        assert _read_latest(service).work_timeline[0].bullets == ["first"]

    def test_add_entry_bullet_missing_entry_is_a_no_op(self) -> None:
        """An unknown entry_id is a logged no-op, not a raise."""
        service = _service()
        entry = Entry(type=ExperienceType.PROJECT, title="Billing", bullets=["first"])
        _seed(service, CareerEngineState(reference_date=_REF, work_timeline=[entry]))

        sid = add_entry_bullet(
            service, app_name=_APP, user_id=_UID, entry_id="nope", text="x"
        )
        assert sid is not None
        assert _read_latest(service).work_timeline[0].bullets == ["first"]


class TestUpdateEntryBullet:
    def test_update_entry_bullet_mutates_correctly(self) -> None:
        service = _service()
        entry = Entry(
            type=ExperienceType.PROJECT, title="Billing rewrite", bullets=["old bullet"]
        )
        _seed(service, CareerEngineState(reference_date=_REF, work_timeline=[entry]))

        sid = update_entry_bullet(
            service,
            app_name=_APP,
            user_id=_UID,
            entry_id=str(entry.entry_id),
            bullet_index=0,
            new_text="new bullet",
        )
        assert sid is not None
        state = _read_latest(service)
        assert state.work_timeline[0].bullets == ["new bullet"]
        assert state.contract_version == CONTRACT_VERSION

    def test_update_entry_bullet_out_of_range(self) -> None:
        service = _service()
        entry = Entry(
            type=ExperienceType.PROJECT, title="Billing rewrite", bullets=["only bullet"]
        )
        _seed(service, CareerEngineState(reference_date=_REF, work_timeline=[entry]))

        # An out-of-range index is a logged no-op — must not raise IndexError.
        sid = update_entry_bullet(
            service,
            app_name=_APP,
            user_id=_UID,
            entry_id=str(entry.entry_id),
            bullet_index=5,
            new_text="ignored",
        )
        assert sid is not None
        assert _read_latest(service).work_timeline[0].bullets == ["only bullet"]

    def test_update_entry_bullet_empty_is_noop(self) -> None:
        service = _service()
        entry = Entry(
            type=ExperienceType.PROJECT, title="Billing rewrite", bullets=["keep me"]
        )
        _seed(service, CareerEngineState(reference_date=_REF, work_timeline=[entry]))

        # A whitespace-only edit must not persist a blank bullet (matches
        # add_manual_entry, which filters empty bullets).
        sid = update_entry_bullet(
            service,
            app_name=_APP,
            user_id=_UID,
            entry_id=str(entry.entry_id),
            bullet_index=0,
            new_text="   ",
        )
        assert sid is not None
        assert _read_latest(service).work_timeline[0].bullets == ["keep me"]

    def test_returns_none_when_no_session(self) -> None:
        service = _service()
        assert (
            update_entry_bullet(
                service,
                app_name=_APP,
                user_id=_UID,
                entry_id="x",
                bullet_index=0,
                new_text="y",
            )
            is None
        )
