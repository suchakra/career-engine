"""Tests for grill coverage (web/coverage.py — CQ-5, AD-18.5).

The bug: the grill marked an entry GRILLED after ONE validated STAR story and moved the
frontier on. So a user who uploaded a résumé with a dozen strong bullets got one of them
interrogated and the other eleven silently ignored, while the grill went off to drill
something else. **Coverage is the product.**
"""

from __future__ import annotations

from schema import Bullet, BulletSource, CareerEngineState, Entry, ExperienceType, StarStory
from web.coverage import CoverageState, bullet_state, entry_coverage, entry_needs_work


def _entry(*bullets: Bullet) -> Entry:
    return Entry(type=ExperienceType.FULL_TIME, title="Staff Engineer", org="Texada",
                 bullets=list(bullets))


def _story(entry: Entry, result: str, *, validated: bool = True) -> StarStory:
    return StarStory(entry_id=str(entry.entry_id), pillar="delivery", result=result,
                     metrics_validated=validated)


class TestBulletState:


    def test_an_accepted_rewrite_is_STRENGTHENED(self) -> None:
        bullet = Bullet(text="Rebuilt CI, cutting failures 40%", source=BulletSource.GRILLED)

        assert bullet_state(bullet, []) is CoverageState.STRENGTHENED

    def test_an_explicitly_skipped_bullet_is_terminal(self) -> None:
        """The escape hatch: the grill may be demanding, but it can't trap the user."""
        bullet = Bullet(text="Attended standups", skipped=True)

        assert bullet_state(bullet, []) is CoverageState.SKIPPED

    def test_an_untouched_bullet_is_UNCOVERED(self) -> None:
        assert bullet_state(Bullet(text="Ran the platform"), []) is CoverageState.UNCOVERED

    def test_a_story_QUANTIFIES_the_bullet_it_says_it_answers(self) -> None:
        """CQ-5b: coverage is decided by a LINK, not by comparing prose."""
        entry = _entry(Bullet(text="Ran CI"))
        story = _story(entry, "Cut deploy failures 40%")  # wording matches NOTHING
        story = story.model_copy(
            update={"answers_bullet_id": str(entry.bullets[0].bullet_id)}
        )

        assert bullet_state(entry.bullets[0], [story]) is CoverageState.QUANTIFIED

    def test_TEXT_alone_never_marks_a_bullet_covered(self) -> None:
        """The heuristic that lied stays dead.

        Two adversarial reviews broke every version of it: containment let an untouched "Ran CI"
        ride on a *different* story ("...teams ran CI/CD 50% faster"); a 4-word floor still let
        "Improved the release process" ride on a story containing that phrase; going
        one-directional then permanently un-covered verbose bullets. A false QUANTIFIED buries
        work the user still has to do. Only the link counts.
        """
        entry = _entry(Bullet(text="Ran CI"))
        # Same words, but the story does NOT claim to answer this bullet.
        story = _story(entry, "Rebuilt releases so teams ran CI/CD 50% faster")

        assert bullet_state(entry.bullets[0], [story]) is CoverageState.UNCOVERED

    def test_an_UNVALIDATED_story_does_not_quantify_even_with_the_link(self) -> None:
        """No metric was actually extracted — the line is still outstanding."""
        entry = _entry(Bullet(text="Ran CI"))
        story = _story(entry, "Ran CI", validated=False).model_copy(
            update={"answers_bullet_id": str(entry.bullets[0].bullet_id)}
        )

        assert bullet_state(entry.bullets[0], [story]) is CoverageState.UNCOVERED





class TestEntryCoverage:
    def test_the_label_tells_the_user_what_is_LEFT(self) -> None:
        entry = _entry(
            Bullet(text="Rebuilt CI, cutting failures 40%", source=BulletSource.GRILLED),
            Bullet(text="Hired and mentored six platform engineers"),
            Bullet(text="Attended standups", skipped=True),
        )

        coverage = entry_coverage(entry, [])

        assert coverage.label == "2 of 3 covered"  # strengthened + skipped; one left
        assert not coverage.is_complete
        assert coverage.uncovered_bullet_ids == [str(entry.bullets[1].bullet_id)]

    def test_a_superseded_bullet_is_not_counted_as_its_own_line(self) -> None:
        """Otherwise coverage would be UNREACHABLE.

        Once a rewrite replaces a line, the original can never be quantified — counting it
        would leave the entry permanently incomplete and the grill stuck on it forever.
        """
        original = Bullet(text="Ran CI")
        rewrite = Bullet(
            text="Rebuilt CI, cutting failures 40%",
            source=BulletSource.GRILLED,
            supersedes=original.bullet_id,
        )
        entry = _entry(original, rewrite)

        coverage = entry_coverage(entry, [])

        assert coverage.total == 1  # only the live bullet
        assert coverage.is_complete


class TestEntryNeedsWork:
    def test_a_GRILLED_entry_with_untouched_bullets_STILL_needs_work(self) -> None:
        """THE bug. One story used to be enough to abandon an entry with 11 lines left."""
        entry = _entry(
            Bullet(text="Rebuilt CI 40% faster", source=BulletSource.GRILLED),
            *[Bullet(text=f"Untouched line number {i}") for i in range(11)],
        )

        assert entry_needs_work(entry, []) is True

    def test_an_entry_whose_every_bullet_is_terminal_is_done(self) -> None:
        entry = _entry(
            Bullet(text="Rebuilt CI 40% faster", source=BulletSource.GRILLED),
            Bullet(text="Attended standups", skipped=True),
        )

        assert entry_needs_work(entry, []) is False

    def test_an_entry_with_no_bullets_has_nothing_to_COVER(self) -> None:
        """Coverage is strictly about supplied material.

        Whether a bare role still needs grilling is a question about its STATUS, which the
        frontier selection already handles. Conflating the two would re-open every finished
        role that happens to carry no bullets — which is exactly what it did on the first cut.
        """
        assert entry_needs_work(_entry(), []) is False


class TestFrontierIsSteeredByCoverage:
    """CQ-5b: the grill no longer abandons an entry it has barely touched."""

    def test_a_GRILLED_entry_with_uncovered_lines_is_NOT_abandoned(self) -> None:
        """THE bug. One validated story used to be enough to walk away from 11 more lines."""
        from schema import EntryStatus
        from workflows.nodes import _next_frontier

        rich = _entry(*[Bullet(text=f"line {i}") for i in range(12)]).model_copy(
            update={"status": EntryStatus.GRILLED}
        )
        other = Entry(type=ExperienceType.PROJECT, title="Side project")
        # A LINKED story — i.e. grilled under v2.11.0, so coverage may judge it. (A GRILLED
        # entry with no links at all is legacy and is deliberately left alone.)
        linked = StarStory(
            entry_id=str(rich.entry_id), pillar="delivery", result="Cut costs 30%",
            metrics_validated=True, answers_bullet_id=str(rich.bullets[0].bullet_id),
        )

        # Old (status-only) rule: the rich entry looks done and is abandoned.
        assert _next_frontier([rich, other], "") == str(other.entry_id)
        # With coverage: 11 lines are still untouched, so it is kept.
        assert _next_frontier([rich, other], "", [linked]) == str(rich.entry_id)

    def test_a_fully_covered_entry_IS_left_behind(self) -> None:
        """Coverage steering must terminate — a finished entry is released."""
        from schema import EntryStatus
        from workflows.nodes import _next_frontier

        done = _entry(Bullet(text="Ran CI", skipped=True)).model_copy(
            update={"status": EntryStatus.GRILLED}
        )

        assert _next_frontier([done], "", []) == ""

    def test_every_successful_turn_retires_exactly_one_bullet(self) -> None:
        """The MONOTONICITY guarantee — this is what makes steering safe.

        Text matching could not promise it: a story worded to match nothing advanced nothing,
        so the frontier would hold the entry and the grill would ask forever. The link means
        each answered question retires the bullet it was asked about, so an entry with N
        uncovered bullets is finished in at most N successful turns.
        """
        from workflows.nodes import _next_uncovered_bullet

        entry = _entry(*[Bullet(text=f"line {i}") for i in range(3)])
        stories: list[StarStory] = []

        seen: list[str] = []
        for _ in range(3):
            target = _next_uncovered_bullet(entry, stories)
            assert target is not None
            seen.append(str(target.bullet_id))
            stories.append(
                StarStory(
                    entry_id=str(entry.entry_id),
                    pillar="delivery",
                    result="some metric 40%",
                    metrics_validated=True,
                    answers_bullet_id=str(target.bullet_id),
                )
            )

        assert len(set(seen)) == 3  # a DIFFERENT bullet each turn — no spinning
        assert _next_uncovered_bullet(entry, stories) is None
        assert entry_coverage(entry, stories).is_complete


def test_a_legacy_document_defaults_skipped_to_False() -> None:
    """`skipped` is additive (v2.10.0) — a document without the key must still load."""
    legacy = {
        "reference_date": "2026-07-12",
        "work_timeline": [
            {
                "type": "full_time",
                "title": "Staff Engineer",
                "bullets": [{"text": "Rebuilt CI"}],  # no `skipped` key
            }
        ],
    }

    state = CareerEngineState.model_validate(legacy)

    assert state.work_timeline[0].bullets[0].skipped is False


def test_skipped_actually_SURVIVES_a_dump_and_reload() -> None:
    """The previous version of this test never round-tripped — it only checked a default.

    (Adversarial review.) What matters is that a skip the user made is still there after the
    state is persisted and read back; otherwise the escape hatch quietly leaks.
    """
    entry = _entry(Bullet(text="Attended standups", skipped=True), Bullet(text="Ran CI"))
    state = CareerEngineState(reference_date="2026-07-12", work_timeline=[entry])

    reloaded = CareerEngineState.model_validate(state.model_dump(mode="json"))

    assert [b.skipped for b in reloaded.work_timeline[0].bullets] == [True, False]
    assert entry_coverage(reloaded.work_timeline[0], []).label == "1 of 2 covered"
