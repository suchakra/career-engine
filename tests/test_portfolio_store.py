"""Tests for the portfolio-mutation seam (Phase 4D/4C).

Uses ADK's real ``InMemorySessionService`` so the state_delta merge semantics
match production (the seam commits via an appended Event, like the workflow's own
nodes). Covers: add-to-existing, add-when-none (creates a session), contract
stamping, title validation, and the grill_frontier jump (incl. the no-session case).
"""

from __future__ import annotations

import asyncio
from typing import cast
from uuid import uuid4

from google.adk.sessions import BaseSessionService, InMemorySessionService

from config import CONTRACT_VERSION
from schema import (
    Bullet,
    BulletSource,
    CareerEngineState,
    Entry,
    EntryStatus,
    ExperienceType,
    StarStory,
)
from web.async_runner import run_async
from web.portfolio_store import (
    accept_bullets,
    add_entry_bullet,
    add_manual_entry,
    amerge_parsed_entries,
    delete_entry,
    delete_entry_bullet,
    delete_star_story,
    merge_work_timeline,
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
            bullets=["Did X", "  ", "Did Y"],  # add_manual_entry takes raw text
        )
        assert _read_latest(service).work_timeline[0].bullet_texts == ["Did X", "Did Y"]

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
            type=ExperienceType.PROJECT, title="Billing rewrite", bullets=[Bullet(text="first")]
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
        assert state.work_timeline[0].bullet_texts == ["first", "second"]  # stripped + appended
        assert state.contract_version == CONTRACT_VERSION

    def test_add_entry_bullet_refuses_a_blank(self) -> None:
        """A whitespace-only bullet is a no-op — never persist an empty line."""
        service = _service()
        entry = Entry(type=ExperienceType.PROJECT, title="Billing", bullets=[Bullet(text="first")])
        _seed(service, CareerEngineState(reference_date=_REF, work_timeline=[entry]))

        add_entry_bullet(
            service, app_name=_APP, user_id=_UID, entry_id=str(entry.entry_id), text="   "
        )
        assert _read_latest(service).work_timeline[0].bullet_texts == ["first"]

    def test_add_entry_bullet_missing_entry_is_a_no_op(self) -> None:
        """An unknown entry_id is a logged no-op, not a raise."""
        service = _service()
        entry = Entry(type=ExperienceType.PROJECT, title="Billing", bullets=[Bullet(text="first")])
        _seed(service, CareerEngineState(reference_date=_REF, work_timeline=[entry]))

        sid = add_entry_bullet(
            service, app_name=_APP, user_id=_UID, entry_id="nope", text="x"
        )
        assert sid is not None
        assert _read_latest(service).work_timeline[0].bullet_texts == ["first"]


class TestBulletIdentityMigration:
    """v2.8.0 persisted bullets as a bare list[str]; v2.9.0 gives them identity."""

    def test_a_legacy_v280_document_loads_and_migrates_losslessly(self) -> None:
        """A REAL v2.8.0-shaped payload (bullets: list[str]) round-trips as Bullets.

        This is the migration that touches live user data, so it is asserted against the
        persisted SHAPE, not against a synthetic model: no line is dropped, none is
        reordered, and every one gets an id.
        """
        legacy = {
            "reference_date": _REF,
            "contract_version": "2.8.0",
            "work_timeline": [
                {
                    "entry_id": str(uuid4()),
                    "type": "full_time",
                    "title": "Staff Engineer",
                    "org": "Texada",
                    "bullets": ["Hired and mentored engineers", "Led the cloud migration"],
                    "status": "grilled",
                }
            ],
        }

        state = CareerEngineState.model_validate(legacy)

        entry = state.work_timeline[0]
        assert entry.bullet_texts == [
            "Hired and mentored engineers",
            "Led the cloud migration",
        ]
        assert all(b.source is BulletSource.PARSED for b in entry.bullets)
        assert len({b.bullet_id for b in entry.bullets}) == 2  # distinct, stable ids

    def test_migration_is_idempotent(self) -> None:
        """Re-validating an already-migrated document must not re-id or duplicate."""
        entry = Entry(type=ExperienceType.PROJECT, title="X", bullets=[Bullet(text="one"), Bullet(text="two")])
        state = CareerEngineState(reference_date=_REF, work_timeline=[entry])

        again = CareerEngineState.model_validate(state.model_dump(mode="json"))

        assert again.work_timeline[0].bullets == entry.bullets  # same ids, same order


class TestUpdateEntryBullet:
    def test_update_entry_bullet_mutates_correctly(self) -> None:
        service = _service()
        entry = Entry(
            type=ExperienceType.PROJECT, title="Billing rewrite", bullets=[Bullet(text="old bullet")]
        )
        _seed(service, CareerEngineState(reference_date=_REF, work_timeline=[entry]))

        sid = update_entry_bullet(
            service,
            app_name=_APP,
            user_id=_UID,
            entry_id=str(entry.entry_id),
            bullet_id=str(entry.bullets[0].bullet_id),
            new_text="new bullet",
        )
        assert sid is not None
        state = _read_latest(service)
        assert state.work_timeline[0].bullet_texts == ["new bullet"]
        assert state.contract_version == CONTRACT_VERSION

    def test_update_entry_bullet_out_of_range(self) -> None:
        service = _service()
        entry = Entry(
            type=ExperienceType.PROJECT, title="Billing rewrite", bullets=[Bullet(text="only bullet")]
        )
        _seed(service, CareerEngineState(reference_date=_REF, work_timeline=[entry]))

        # An UNKNOWN bullet_id is a logged no-op — must not raise (v2.9.0: ids, not
        # indices, so a stale client can no longer edit whatever line happens to sit at
        # that position).
        sid = update_entry_bullet(
            service,
            app_name=_APP,
            user_id=_UID,
            entry_id=str(entry.entry_id),
            bullet_id=str(uuid4()),
            new_text="ignored",
        )
        assert sid is not None
        assert _read_latest(service).work_timeline[0].bullet_texts == ["only bullet"]

    def test_update_entry_bullet_empty_is_noop(self) -> None:
        service = _service()
        entry = Entry(
            type=ExperienceType.PROJECT, title="Billing rewrite", bullets=[Bullet(text="keep me")]
        )
        _seed(service, CareerEngineState(reference_date=_REF, work_timeline=[entry]))

        # A whitespace-only edit must not persist a blank bullet (matches
        # add_manual_entry, which filters empty bullets).
        sid = update_entry_bullet(
            service,
            app_name=_APP,
            user_id=_UID,
            entry_id=str(entry.entry_id),
            bullet_id=str(entry.bullets[0].bullet_id),
            new_text="   ",
        )
        assert sid is not None
        assert _read_latest(service).work_timeline[0].bullet_texts == ["keep me"]

    def test_returns_none_when_no_session(self) -> None:
        service = _service()
        assert (
            update_entry_bullet(
                service,
                app_name=_APP,
                user_id=_UID,
                entry_id="x",
                bullet_id=str(uuid4()),
                new_text="y",
            )
            is None
        )


class TestMergeWorkTimeline:
    """CQ-2: a résumé RE-upload must merge, never clobber.

    Before this, ``POST /api/grill/resume`` called ``session.create`` — which is
    last-write-wins — so a second upload silently destroyed every entry, every STAR
    story, and every hour of grilling.
    """

    def _role(self, title: str, org: str, *, bullets: list[str], status: EntryStatus) -> Entry:
        return Entry(
            type=ExperienceType.FULL_TIME,
            title=title,
            org=org,
            bullets=[Bullet(text=b) for b in bullets],
            status=status,
        )

    def test_a_matched_role_keeps_its_id_stories_and_grilled_status(self) -> None:
        """The whole point: re-uploading must not orphan grilled work."""
        existing = self._role(
            "Staff Engineer", "Texada", bullets=["Led the migration"], status=EntryStatus.GRILLED
        )
        # The same role as read off an updated résumé: new object, new ids, one new line.
        parsed = self._role(
            "  staff engineer  ",  # noisier case/spacing — must still match
            "TEXADA",
            bullets=["Led the migration", "Cut cloud spend 30%"],
            status=EntryStatus.NEEDS_QUANTIFYING,
        )

        merged, added = merge_work_timeline([existing], [parsed])

        assert added == []  # not a new role
        assert len(merged) == 1
        kept = merged[0]
        assert kept.entry_id == existing.entry_id  # STAR stories stay linked
        assert kept.status is EntryStatus.GRILLED  # never demoted back to ungrilled
        assert kept.bullet_texts == ["Led the migration", "Cut cloud spend 30%"]  # unioned

    def test_a_new_role_is_appended_ungrilled(self) -> None:
        existing = self._role("Staff Engineer", "Texada", bullets=[], status=EntryStatus.GRILLED)
        parsed = self._role(
            "Senior SDE", "Oracle", bullets=["Ran the DevOps team"], status=EntryStatus.NEEDS_QUANTIFYING
        )

        merged, added = merge_work_timeline([existing], [parsed])

        assert [e.title for e in merged] == ["Staff Engineer", "Senior SDE"]
        assert [e.entry_id for e in added] == [parsed.entry_id]
        assert merged[1].status is EntryStatus.NEEDS_QUANTIFYING

    def test_a_role_this_resume_omits_is_KEPT(self) -> None:
        """A résumé is a curated subset of a career, not a delete list."""
        keep = self._role("Program Manager", "Oracle", bullets=["Shipped X"], status=EntryStatus.GRILLED)
        parsed = self._role("Senior SDE", "Oracle", bullets=[], status=EntryStatus.NEEDS_QUANTIFYING)

        merged, _ = merge_work_timeline([keep], [parsed])

        assert keep.entry_id in {e.entry_id for e in merged}

    def test_a_noisy_parse_repeating_a_line_does_not_duplicate_it(self) -> None:
        """Duplicates WITHIN one parsed résumé must also collapse.

        Regression (Copilot): the filter compared each candidate bullet only against the
        EXISTING entry's lines, so if a noisy parse emitted the same line twice in one
        résumé, both copies were appended.
        """
        existing = self._role("Staff Engineer", "Texada", bullets=[], status=EntryStatus.GRILLED)
        noisy = self._role(
            "Staff Engineer", "Texada",
            bullets=["Cut cloud spend 30%", "  cut cloud spend 30%  ", "Hired six engineers"],
            status=EntryStatus.NEEDS_QUANTIFYING,
        )

        merged, _ = merge_work_timeline([existing], [noisy])

        assert merged[0].bullet_texts == ["Cut cloud spend 30%", "Hired six engineers"]

    def test_bullets_are_not_duplicated_on_re_upload(self) -> None:
        """Re-uploading the SAME résumé must be a no-op, not a doubling."""
        existing = self._role(
            "Staff Engineer", "Texada",
            bullets=["Led the migration", "Hired six engineers"],
            status=EntryStatus.GRILLED,
        )
        same_again = self._role(
            "Staff Engineer", "Texada",
            bullets=["  led the migration  ", "Hired six engineers"],  # same lines, noisier
            status=EntryStatus.NEEDS_QUANTIFYING,
        )

        merged, added = merge_work_timeline([existing], [same_again])

        assert added == []
        assert merged[0].bullet_texts == ["Led the migration", "Hired six engineers"]
        assert merged[0].entry_id == existing.entry_id


class TestMergeParsedEntriesIntoSession:
    def test_merge_preserves_every_star_story_and_aims_the_grill_at_new_work(self) -> None:
        """End-to-end over the session: NO story may be lost, and the frontier moves."""
        service = _service()
        job = Entry(
            type=ExperienceType.FULL_TIME, title="Staff Engineer", org="Texada",
            bullets=[Bullet(text="Led the migration")], status=EntryStatus.GRILLED,
        )
        story = StarStory(
            entry_id=str(job.entry_id), pillar="delivery",
            result="Cut deploy failures 40%", metrics_validated=True,
        )
        _seed(
            service,
            CareerEngineState(
                reference_date=_REF,
                work_timeline=[job],
                extracted_star_stories=[story],
                current_question="What did that migration save?",
            ),
        )

        # Upload #2: the same role (updated) plus a role we have never seen.
        parsed = [
            Entry(type=ExperienceType.FULL_TIME, title="Staff Engineer", org="Texada",
                  bullets=[Bullet(text="Cut cloud spend 30%")]),
            Entry(type=ExperienceType.FULL_TIME, title="Senior SDE", org="Oracle",
                  bullets=[Bullet(text="Ran the DevOps team")]),
        ]
        sid = run_async(
            amerge_parsed_entries(
                service, app_name=_APP, user_id=_UID, entries=parsed
            )
        )
        assert sid is not None

        state = _read_latest(service)
        # Nothing destroyed: the story survives and still points at the kept entry.
        assert len(state.extracted_star_stories) == 1
        assert state.extracted_star_stories[0].entry_id == str(job.entry_id)
        kept = next(e for e in state.work_timeline if e.entry_id == job.entry_id)
        assert kept.status is EntryStatus.GRILLED
        assert kept.bullet_texts == ["Led the migration", "Cut cloud spend 30%"]
        # The new role is there, and the grill is aimed at it (stale question cleared).
        new_role = next(e for e in state.work_timeline if e.title == "Senior SDE")
        assert state.grill_frontier == str(new_role.entry_id)
        assert state.current_question == ""

    def test_returns_none_when_there_is_no_session_to_merge_into(self) -> None:
        """A FIRST upload has nothing to merge into — the caller creates instead."""
        service = _service()
        assert (
            run_async(
                amerge_parsed_entries(service, app_name=_APP, user_id=_UID, entries=[])
            )
            is None
        )


class TestDeleteEntryBullet:
    def test_removes_only_the_named_bullet(self) -> None:
        service = _service()
        entry = Entry(
            type=ExperienceType.PROJECT,
            title="Billing",
            bullets=[Bullet(text="keep me"), Bullet(text="delete me")],
        )
        _seed(service, CareerEngineState(reference_date=_REF, work_timeline=[entry]))

        sid = delete_entry_bullet(
            service,
            app_name=_APP,
            user_id=_UID,
            entry_id=str(entry.entry_id),
            bullet_id=str(entry.bullets[1].bullet_id),
        )

        assert sid is not None
        assert _read_latest(service).work_timeline[0].bullet_texts == ["keep me"]

    def test_unknown_bullet_is_a_no_op(self) -> None:
        service = _service()
        entry = Entry(type=ExperienceType.PROJECT, title="Billing", bullets=[Bullet(text="keep")])
        _seed(service, CareerEngineState(reference_date=_REF, work_timeline=[entry]))

        sid = delete_entry_bullet(
            service, app_name=_APP, user_id=_UID,
            entry_id=str(entry.entry_id), bullet_id=str(uuid4()),
        )

        assert sid is not None  # idempotent, not an error
        assert _read_latest(service).work_timeline[0].bullet_texts == ["keep"]

    def test_returns_none_when_no_session(self) -> None:
        service = _service()
        assert (
            delete_entry_bullet(
                service, app_name=_APP, user_id=_UID, entry_id="x", bullet_id=str(uuid4())
            )
            is None
        )


class TestDeleteEntry:
    def test_deleting_an_entry_CASCADES_to_its_star_stories(self) -> None:
        """Leaving the stories behind would orphan them against a dead entry_id.

        An orphan still counts toward the portfolio meter and can still be selected onto
        a résumé under a role the user just removed — so the delete must cascade.
        """
        service = _service()
        doomed = Entry(type=ExperienceType.PROJECT, title="Doomed", org="Acme")
        kept = Entry(type=ExperienceType.PROJECT, title="Kept", org="Acme")
        _seed(
            service,
            CareerEngineState(
                reference_date=_REF,
                work_timeline=[doomed, kept],
                extracted_star_stories=[
                    StarStory(entry_id=str(doomed.entry_id), pillar="delivery", result="A"),
                    StarStory(entry_id=str(kept.entry_id), pillar="delivery", result="B"),
                ],
            ),
        )

        sid = delete_entry(service, app_name=_APP, user_id=_UID, entry_id=str(doomed.entry_id))

        assert sid is not None
        state = _read_latest(service)
        assert [e.title for e in state.work_timeline] == ["Kept"]
        # The doomed entry's story is gone; the other one is untouched.
        assert [s.result for s in state.extracted_star_stories] == ["B"]
        assert all(s.entry_id != str(doomed.entry_id) for s in state.extracted_star_stories)

    def test_deleting_the_frontier_entry_clears_every_trace_of_its_grill(self) -> None:
        """No stale grill state may survive the entry it belonged to.

        The dangerous one is ``pending_user_answer``: it was typed ABOUT the deleted
        entry. Left in place, the next turn would consume it as the answer for whatever
        entry becomes the new frontier and attach a STAR story to the WRONG role.
        ``grill_attempts`` / ``grill_answers`` are keyed by entry_id and would otherwise
        linger forever against an id that no longer exists.
        """
        service = _service()
        doomed = Entry(type=ExperienceType.PROJECT, title="Doomed")
        other = Entry(type=ExperienceType.PROJECT, title="Other")
        _seed(
            service,
            CareerEngineState(
                reference_date=_REF,
                work_timeline=[doomed, other],
                grill_frontier=str(doomed.entry_id),
                current_question="Tell me about the doomed project?",
                pending_user_answer="We cut latency by 40%",
                grill_attempts={str(doomed.entry_id): 2, str(other.entry_id): 1},
                grill_answers={
                    str(doomed.entry_id): ["about the doomed one"],
                    str(other.entry_id): ["about the other one"],
                },
            ),
        )

        delete_entry(service, app_name=_APP, user_id=_UID, entry_id=str(doomed.entry_id))

        state = _read_latest(service)
        assert [e.title for e in state.work_timeline] == ["Other"]
        assert state.grill_frontier == ""
        assert state.current_question == ""
        assert state.pending_user_answer == ""  # must not land on the surviving entry
        # The deleted entry's buffers are pruned; the survivor's are untouched.
        assert state.grill_attempts == {str(other.entry_id): 1}
        assert state.grill_answers == {str(other.entry_id): ["about the other one"]}

    def test_unknown_entry_is_a_no_op(self) -> None:
        service = _service()
        entry = Entry(type=ExperienceType.PROJECT, title="Keep")
        _seed(service, CareerEngineState(reference_date=_REF, work_timeline=[entry]))

        sid = delete_entry(service, app_name=_APP, user_id=_UID, entry_id="nope")

        assert sid is not None
        assert len(_read_latest(service).work_timeline) == 1

    def test_returns_none_when_no_session(self) -> None:
        service = _service()
        assert delete_entry(service, app_name=_APP, user_id=_UID, entry_id="x") is None


class TestAcceptBullets:
    def test_an_accepted_rewrite_REPLACES_the_original(self) -> None:
        """CQ-4: the résumé must never carry both the polished line and the one it replaced."""
        service = _service()
        original = Bullet(text="Ran CI")
        keep = Bullet(text="Hired six engineers")
        entry = Entry(type=ExperienceType.PROJECT, title="Platform", bullets=[original, keep])
        _seed(service, CareerEngineState(reference_date=_REF, work_timeline=[entry]))

        polished = Bullet(
            text="Rebuilt CI, cutting deploy failures 40%",
            source=BulletSource.GRILLED,
            supersedes=original.bullet_id,
        )
        sid = accept_bullets(
            service, app_name=_APP, user_id=_UID,
            entry_id=str(entry.entry_id), bullets=[polished],
        )

        assert sid is not None
        bullets = _read_latest(service).work_timeline[0].bullets
        texts = [b.text for b in bullets]
        assert "Ran CI" not in texts  # superseded → gone, resolved BY ID
        assert texts == ["Hired six engineers", "Rebuilt CI, cutting deploy failures 40%"]
        assert bullets[-1].source is BulletSource.GRILLED

    def test_a_story_derived_bullet_is_ADDED_without_removing_anything(self) -> None:
        service = _service()
        entry = Entry(
            type=ExperienceType.PROJECT, title="Platform", bullets=[Bullet(text="Ran CI")]
        )
        _seed(service, CareerEngineState(reference_date=_REF, work_timeline=[entry]))

        accept_bullets(
            service, app_name=_APP, user_id=_UID, entry_id=str(entry.entry_id),
            bullets=[Bullet(text="Cut deploy failures 40%", source=BulletSource.GRILLED)],
        )

        assert _read_latest(service).work_timeline[0].bullet_texts == [
            "Ran CI",
            "Cut deploy failures 40%",
        ]

    def test_returns_none_when_no_session(self) -> None:
        service = _service()
        assert (
            accept_bullets(service, app_name=_APP, user_id=_UID, entry_id="x", bullets=[])
            is None
        )
