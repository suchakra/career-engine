"""Every résumé line carries its identity (CQ-6 / web.resume_builder.ResumeLine).

A résumé line used to be a bare ``str``, and that one fact was the ceiling on three separate
bugs — each of which is pinned here by the state that reproduces it:

- **The master résumé listed one achievement three times** (the raw grill text, the original
  parsed line, and the copywriter rewrite the user approved), because an accepted rewrite
  recorded nothing about the story it was written for.
- **The tailored résumé ignored the uploaded résumé entirely** — a user who uploaded a strong
  CV and tailored it before grilling got an empty document. The same bug was reported and fixed
  for the *master* résumé; it was still live here.
- **The tailored résumé shipped raw grill text** even when the user had approved better prose,
  making a liar of CQ-4's promise that no unreviewed text reaches a PDF.

Two adversarial pre-execution reviews then caught the two ways the *fix* could be worse than
the bug (``TestLegacyData`` and ``TestCoverageDoesNotReopenFinishedWork``). Those are the tests
to read first: both scenarios are what the live database actually contains.
"""

from __future__ import annotations

import json
from typing import cast
from uuid import uuid4

from integration.model_client import GeminiModelClient
from schema import (
    Bullet,
    BulletSource,
    CareerEngineState,
    Entry,
    EntryStatus,
    ExperienceType,
    StarStory,
)
from tests.test_integration import ScriptedNodeClient
from web.coverage import CoverageState, bullet_state, entry_coverage
from web.resume_builder import (
    Contact,
    master_structured_resume,
    resume_lines,
    tailor_structured_resume,
)


def _job(**kw: object) -> Entry:
    return Entry(
        type=ExperienceType.FULL_TIME, title="Staff Engineer", org="Acme",
        start_date="2020", end_date="2023", status=EntryStatus.GRILLED, **kw,  # type: ignore[arg-type]
    )


def _story(entry: Entry, result: str, *, answers: str = "") -> StarStory:
    return StarStory(
        story_id=uuid4(), entry_id=str(entry.entry_id), pillar="delivery",
        result=result, metrics_validated=True, answers_bullet_id=answers,
    )


def _texts(state: CareerEngineState) -> list[str]:
    return [line.text for line in master_structured_resume(state).experience[0].bullets]


def _tailored(state: CareerEngineState, selected: list[str] | None = None) -> list[str]:
    """Tailor with the model selecting `selected` (default: whatever it likes = fall back to all)."""
    client = ScriptedNodeClient(
        responses={
            "tailoring a candidate's real": json.dumps(
                {"tailored_summary": "S", "skills": [], "selected_achievement_ids": selected or []}
            )
        }
    )
    resume = tailor_structured_resume(
        state, "JD", Contact(), client=cast(GeminiModelClient, client)
    )
    return [line.text for role in resume.experience for line in role.bullets]


class TestTheApprovedLineIsTheLineThatShips:
    """CQ-4's promise, finally kept: the user's approved prose reaches the PDF — once."""

    def test_an_achievement_the_user_polished_is_listed_ONCE(self) -> None:
        """THE bug. Three lines for one achievement — reproduced before the fix.

        The copywriter's story-derived proposal was accepted as a bullet that superseded
        nothing and recorded nothing, so the assembler could not know it and the raw
        ``story.result`` were the same thing. Text dedup could never have caught it either:
        the better the copywriter does its job, the LESS the rewrite looks like the original.
        """
        parsed = Bullet(text="Ran CI for the platform team")
        story = _story(_job(), "Cut deploy failures 40%")
        polished = Bullet(  # what the user clicked "Keep" on
            text="Rebuilt CI from scratch, cutting deploy failures 40%",
            source=BulletSource.GRILLED,
            derived_from_story_id=str(story.story_id),
        )
        entry = _job(bullets=[parsed, polished])
        story = story.model_copy(
            update={"entry_id": str(entry.entry_id), "answers_bullet_id": str(parsed.bullet_id)}
        )
        state = CareerEngineState(work_timeline=[entry], extracted_star_stories=[story])

        assert _texts(state) == ["Rebuilt CI from scratch, cutting deploy failures 40%"]

    def test_the_TAILORED_resume_uses_the_approved_line_not_the_raw_grill_text(self) -> None:
        """The tailored résumé is the product. It was shipping the grill's working notes."""
        story = _story(_job(), "Cut deploy failures 40%")
        polished = Bullet(
            text="Rebuilt CI from scratch, cutting deploy failures 40%",
            source=BulletSource.GRILLED,
            derived_from_story_id=str(story.story_id),
        )
        entry = _job(bullets=[polished])
        story = story.model_copy(update={"entry_id": str(entry.entry_id)})
        state = CareerEngineState(work_timeline=[entry], extracted_star_stories=[story])

        assert _tailored(state) == ["Rebuilt CI from scratch, cutting deploy failures 40%"]

    def test_only_ONE_bullet_speaks_for_a_story_even_if_two_claim_to(self) -> None:
        """Two live bullets CAN name the same story — the loser must not come back as its own line.

        (Adversarial review.) The user accepts a copywriter rewrite of story S in Portfolio,
        then overwrites S's line again from a STALE tailor preview. Both bullets now derive
        from S. Whichever the assembler picks, the other must NOT be emitted separately — or
        the duplicate bug walks back in through the front door.
        """
        story = _story(_job(), "Cut deploy failures 40%")
        first = Bullet(text="Rebuilt CI, cutting failures 40%", source=BulletSource.GRILLED,
                       derived_from_story_id=str(story.story_id))
        second = Bullet(text="Rebuilt CI end to end, cutting deploy failures 40%",
                        source=BulletSource.USER, derived_from_story_id=str(story.story_id))
        entry = _job(bullets=[first, second])
        story = story.model_copy(update={"entry_id": str(entry.entry_id)})
        state = CareerEngineState(work_timeline=[entry], extracted_star_stories=[story])

        # Exactly one line, and it is the LAST writer — the only deterministic tiebreak
        # available (Bullet has no timestamp), so it is document order.
        assert _texts(state) == ["Rebuilt CI end to end, cutting deploy failures 40%"]


class TestTheUploadedResumeIsNotThrownAway:
    def test_an_ungrilled_uploaded_resume_STILL_TAILORS(self) -> None:
        """Upload a good résumé, tailor it before grilling → you used to get NOTHING.

        The tailor's catalog was validated STAR stories only, so a user with no stories had an
        empty catalog and an empty document. This is the same bug the operator reported as
        "master resume ignores all original resume" — fixed for the master, still live here.
        """
        entry = _job(bullets=[Bullet(text="Ran the platform team"), Bullet(text="Cut cloud spend 30%")])
        state = CareerEngineState(work_timeline=[entry])

        assert _tailored(state) == ["Ran the platform team", "Cut cloud spend 30%"]

    def test_a_PINNED_role_backed_only_by_ungrilled_bullets_survives_selection(self) -> None:
        """4E: pinning says "this role matters". It must outrank the model's selection.

        (Adversarial review.) The old pinned-inclusion mapped ids through a story→entry map,
        which returns "" for a bullet-backed line — silently defeating 4E for exactly the
        uploaded-résumé users this change exists to serve.
        """
        pinned = Entry(
            type=ExperienceType.FULL_TIME, title="Lead", org="BitCrafty",
            highlighted=True, bullets=[Bullet(text="Grew revenue 3x")],
        )
        other = _job()
        story = _story(other, "Cut latency 40%")
        state = CareerEngineState(
            work_timeline=[other, pinned], extracted_star_stories=[story]
        )

        # The model picks only the OTHER role's story; the pinned role must still appear.
        assert "Grew revenue 3x" in _tailored(state, selected=[f"story:{story.story_id}"])


class TestLegacyData:
    """The live database is ALL legacy. These are the tests that stop a day-one regression."""

    def test_a_link_less_story_still_dedups_its_original_line(self) -> None:
        """SHOWSTOPPER, caught on paper. Every pre-v2.11.0 story has an EMPTY answers_bullet_id.

        An earlier draft of CQ-6 deleted the text-containment dedup outright, reasoning that
        the id link had replaced it. But the link does not exist on any legacy story — and it
        never can, since which line a story answered is not recoverable. Dedup by link alone
        would therefore have deduped NOTHING on real data: every grilled role of every
        returning user would list its achievement twice on day one.

        So ``_covers`` survives, scoped to exactly this case: a story with no link.
        """
        bullet = Bullet(text="Managed CI for 40 services")
        entry = _job(bullets=[bullet])
        legacy = _story(entry, "Managed CI for 40 services, cutting build time 35%")  # answers=""
        state = CareerEngineState(work_timeline=[entry], extracted_star_stories=[legacy])

        assert legacy.answers_bullet_id == ""  # this is what all live data looks like
        assert _texts(state) == ["Managed CI for 40 services, cutting build time 35%"]

    def test_a_LINKED_story_is_trusted_over_the_prose(self) -> None:
        """Where the link exists we use it, and we do NOT fall back to comparing text.

        A linked story that answers a DIFFERENT bullet says nothing about this one — even if
        the words happen to overlap. That is the whole reason the link was introduced.
        """
        answered = Bullet(text="Ran CI")
        untouched = Bullet(text="Ran the release process")
        entry = _job(bullets=[answered, untouched])
        story = _story(entry, "Ran CI and the release process, cutting lead time 35%",
                       answers=str(answered.bullet_id))
        state = CareerEngineState(work_timeline=[entry], extracted_star_stories=[story])

        lines = _texts(state)
        assert lines[0] == "Ran CI and the release process, cutting lead time 35%"
        # "Ran the release process" is CONTAINED in the story's text — but the story says it
        # answers a different bullet, so this line is still outstanding and must be shown.
        assert "Ran the release process" in lines


class TestCoverageDoesNotReopenFinishedWork:
    """The CQ-5b failure, which this feature could trivially have shipped again."""

    def test_a_bullet_written_FOR_a_validated_story_is_covered(self) -> None:
        """Otherwise polishing a line UN-covers it and the grill comes back for a number.

        The rewrite is stored as a NEW bullet, and no story's ``answers_bullet_id`` names it.
        The bullet is built as ``copywriter.accept()`` really builds it — GRILLED **and**
        linked. (An earlier version of this test used ``source=USER``, a shape no write path
        produces, so it pinned nothing real. See ``test_coverage.py`` for that whole story.)
        """
        story = _story(_job(), "Cut deploy failures 40%")
        polished = Bullet(text="Rebuilt CI, cutting deploy failures 40%",
                          source=BulletSource.GRILLED,
                          derived_from_story_id=str(story.story_id))
        entry = _job(bullets=[polished])
        story = story.model_copy(update={"entry_id": str(entry.entry_id)})

        assert bullet_state(polished, [story]) is CoverageState.QUANTIFIED
        assert entry_coverage(entry, [story]).is_complete

    def test_NEITHER_persist_destination_re_opens_a_finished_entry_AT_THE_ROUTER(self) -> None:
        """Drive the ROUTER, not the pure helper. This is the CQ-5b lesson, literally.

        CQ-5b was green across 839 tests while the feature did nothing, because coverage was
        wired into the grill node but NOT into `discovery_graph._has_pending_work` — the gate
        that actually decides whether the run goes back to the grill or finalizes. A coverage
        rule that only the unit tests exercise proves nothing about what the user experiences.
        """
        from workflows.discovery_graph import _has_pending_work
        from workflows.nodes import entry_still_needs_grilling

        original = Bullet(text="Managed CI for 40 services")
        entry = _job(bullets=[original])  # _job() is already GRILLED
        story = _story(entry, "Managed CI for 40 services, cutting build 35%",
                       answers=str(original.bullet_id))
        state = CareerEngineState(work_timeline=[entry], extracted_star_stories=[story])
        assert not entry_still_needs_grilling(entry, [story])  # finished, before any edit

        # (a) OVERWRITE an existing bullet: in place, so the id — and every link to it — holds.
        original.text = "Ran CI for 40 services, cutting build time 35%"
        original.source = BulletSource.USER
        assert not entry_still_needs_grilling(entry, [story])
        assert not _has_pending_work(state)

        # (b) OVERWRITE a story-only line: a NEW bullet, which is exactly the shape that
        #     re-opened finished portfolios in CQ-5b — unless it carries the story link.
        second = _story(entry, "Cut cloud spend 30%")
        state.extracted_star_stories.append(second)
        entry.bullets.append(
            Bullet(text="Cut cloud spend 30% by right-sizing", source=BulletSource.USER,
                   derived_from_story_id=str(second.story_id))
        )
        stories = state.extracted_star_stories
        assert not entry_still_needs_grilling(entry, stories)
        assert not _has_pending_work(state)

    def test_a_DANGLING_link_does_not_silently_cover_a_bullet(self) -> None:
        """The story was deleted. A bullet claiming to speak for it is covered by nothing.

        The store CLEARS the link when a story is deleted (see test_portfolio_store); this
        pins the coverage side — a link to a story that isn't there must never read as
        covered, or a deleted metric leaves a permanently-and-falsely-finished line.
        """
        orphan = Bullet(text="Rebuilt CI", source=BulletSource.USER,
                        derived_from_story_id=str(uuid4()))

        assert bullet_state(orphan, []) is CoverageState.UNCOVERED


class TestOverwritingALineActuallyChangesTheResume:
    """CQ-6b. The CQ-5b lesson: assert the DOCUMENT changed, never that the endpoint said 204.

    A persist that returns success while the résumé keeps rendering the old text is precisely
    the failure this codebase has shipped three times.
    """

    def test_overwriting_a_STORY_line_replaces_it_in_the_rendered_resume(self) -> None:
        """No bullet existed: the grill wrote this line and the copywriter never polished it.

        The user's text is stored as a bullet that SPEAKS FOR the story, and the assembler
        renders it INSTEAD of the raw grill text — in the master and in the tailored résumé.
        """
        entry = _job()
        story = _story(entry, "Cut deploy failures 40%")
        state = CareerEngineState(work_timeline=[entry], extracted_star_stories=[story])
        assert _texts(state) == ["Cut deploy failures 40%"]  # before

        # …the user overwrites it in the tailor preview (what the route persists):
        entry.bullets = [
            Bullet(
                text="Rebuilt CI end to end, cutting deploy failures 40%",
                source=BulletSource.USER,
                derived_from_story_id=str(story.story_id),
            )
        ]

        assert _texts(state) == ["Rebuilt CI end to end, cutting deploy failures 40%"]
        assert _tailored(state) == ["Rebuilt CI end to end, cutting deploy failures 40%"]
        # …and the entry did NOT re-open: the bullet borrows the story's validated metric.
        assert entry_coverage(entry, [story]).is_complete

    def test_UNDOING_a_story_line_overwrite_restores_the_original(self) -> None:
        """Overwrite is destructive, so undo must be real.

        Deleting the bullet we created makes the assembler fall back to the story's own text —
        which is exactly the line that was there before. (Without this, a user who reworded a
        line to echo one company's vocabulary has permanently degraded every future résumé and
        has NO way back: the in-place edit destroys the old wording in the store.)
        """
        entry = _job()
        story = _story(entry, "Cut deploy failures 40%")
        state = CareerEngineState(work_timeline=[entry], extracted_star_stories=[story])
        entry.bullets = [
            Bullet(text="A JD-flavoured rewording", source=BulletSource.USER,
                   derived_from_story_id=str(story.story_id))
        ]
        assert _texts(state) == ["A JD-flavoured rewording"]

        entry.bullets = []  # what DELETE /bullet/{id} does

        assert _texts(state) == ["Cut deploy failures 40%"]

    def test_overwriting_a_BULLET_line_keeps_its_id_and_its_coverage(self) -> None:
        """In-place, so every link that pointed at this line still does.

        A `supersedes` overwrite would mint a NEW bullet that no story names → UNCOVERED →
        the grill re-opens a finished entry and demands a number for the line the user just
        polished. Keeping the id means `answers_bullet_id`, coverage and the dedup all stay
        pointed at the right thing.
        """
        bullet = Bullet(text="Managed CI for 40 services")
        entry = _job(bullets=[bullet])
        story = _story(entry, "Managed CI for 40 services, cutting build time 35%",
                       answers=str(bullet.bullet_id))
        before = entry_coverage(entry, [story])

        bullet.text = "Managed CI for 40 services"  # in-place edit (same bullet_id)
        bullet.source = BulletSource.USER

        after = entry_coverage(entry, [story])
        assert after.is_complete is before.is_complete
        assert after.label == before.label  # coverage did NOT regress
        assert bullet_state(bullet, [story]) is CoverageState.QUANTIFIED


def test_the_resume_lines_of_an_entry_are_the_tailors_catalog() -> None:
    """One definition of "this role's material", so the catalog and the document cannot drift.

    The model can only select something that will actually render, and anything renderable can
    be selected — because they are literally the same list.
    """
    entry = _job(bullets=[Bullet(text="Mentored six engineers")])
    story = _story(entry, "Cut latency 40%")
    state = CareerEngineState(work_timeline=[entry], extracted_star_stories=[story])

    lines = resume_lines(state)[str(entry.entry_id)]

    assert [line.text for line in lines] == ["Cut latency 40%", "Mentored six engineers"]
    assert lines[0].story_id == str(story.story_id) and lines[0].bullet_id == ""
    assert lines[1].bullet_id == str(entry.bullets[0].bullet_id) and lines[1].story_id == ""
