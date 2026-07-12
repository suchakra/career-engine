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
    def test_a_bullet_a_validated_story_covers_is_QUANTIFIED(self) -> None:
        entry = _entry(Bullet(text="Rebuilt CI"))
        story = _story(entry, "Rebuilt CI, cutting deploy failures 40%")

        assert bullet_state(entry.bullets[0], [story]) is CoverageState.QUANTIFIED

    def test_an_UNVALIDATED_story_does_not_count_as_quantified(self) -> None:
        """No metric was actually extracted — the line is still outstanding."""
        entry = _entry(Bullet(text="Rebuilt CI"))
        story = _story(entry, "Rebuilt CI, cutting deploy failures 40%", validated=False)

        assert bullet_state(entry.bullets[0], [story]) is CoverageState.UNCOVERED

    def test_an_accepted_rewrite_is_STRENGTHENED(self) -> None:
        bullet = Bullet(text="Rebuilt CI, cutting failures 40%", source=BulletSource.GRILLED)

        assert bullet_state(bullet, []) is CoverageState.STRENGTHENED

    def test_an_explicitly_skipped_bullet_is_terminal(self) -> None:
        """The escape hatch: the grill may be demanding, but it can't trap the user."""
        bullet = Bullet(text="Attended standups", skipped=True)

        assert bullet_state(bullet, []) is CoverageState.SKIPPED

    def test_an_untouched_bullet_is_UNCOVERED(self) -> None:
        assert bullet_state(Bullet(text="Ran the platform"), []) is CoverageState.UNCOVERED


class TestEntryCoverage:
    def test_the_label_tells_the_user_what_is_LEFT(self) -> None:
        entry = _entry(
            Bullet(text="Rebuilt CI"),
            Bullet(text="Hired six engineers"),
            Bullet(text="Attended standups", skipped=True),
        )
        story = _story(entry, "Rebuilt CI, cutting deploy failures 40%")

        coverage = entry_coverage(entry, [story])

        assert coverage.label == "2 of 3 covered"  # quantified + skipped; one left
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
            Bullet(text="Rebuilt CI"),
            *[Bullet(text=f"Untouched line {i}") for i in range(11)],
        )
        story = _story(entry, "Rebuilt CI, cutting deploy failures 40%")

        assert entry_needs_work(entry, [story]) is True

    def test_an_entry_whose_every_bullet_is_terminal_is_done(self) -> None:
        entry = _entry(
            Bullet(text="Rebuilt CI"),
            Bullet(text="Attended standups", skipped=True),
            Bullet(text="Hired six", source=BulletSource.GRILLED),
        )
        story = _story(entry, "Rebuilt CI, cutting deploy failures 40%")

        assert entry_needs_work(entry, [story]) is False

    def test_an_entry_with_no_bullets_has_nothing_to_COVER(self) -> None:
        """Coverage is strictly about supplied material.

        Whether a bare role still needs grilling is a question about its STATUS, which the
        frontier selection already handles. Conflating the two would re-open every finished
        role that happens to carry no bullets — which is exactly what it did on the first cut.
        """
        assert entry_needs_work(_entry(), []) is False


class TestFrontierHonoursCoverage:
    def test_the_frontier_does_not_abandon_an_entry_with_uncovered_lines(self) -> None:
        from workflows.nodes import _next_frontier

        rich = _entry(*[Bullet(text=f"line {i}") for i in range(12)])
        from schema import EntryStatus

        rich = rich.model_copy(update={"status": EntryStatus.GRILLED})
        other = Entry(type=ExperienceType.PROJECT, title="Side project")
        story = _story(rich, "line 0, quantified 40%")

        # Without stories the old status-only rule applies and the rich entry looks done…
        assert _next_frontier([rich, other], "") == str(other.entry_id)
        # …but with coverage, the rich entry outranks the side project (recent + substantive).
        assert _next_frontier([rich, other], "", [story]) == str(rich.entry_id)

    def test_a_fully_covered_grilled_entry_is_left_behind(self) -> None:
        from schema import EntryStatus
        from workflows.nodes import _next_frontier

        done = _entry(Bullet(text="Rebuilt CI", skipped=True)).model_copy(
            update={"status": EntryStatus.GRILLED}
        )
        assert _next_frontier([done], "", []) == ""


def test_coverage_survives_a_state_round_trip() -> None:
    """`skipped` is additive (v2.10.0) — a document without it defaults to False."""
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
