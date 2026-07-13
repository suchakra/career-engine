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

    def test_a_grilled_story_does_NOT_mark_a_bullet_covered_by_TEXT(self) -> None:
        """There is deliberately no QUANTIFIED-by-text-matching state — it lied.

        Two adversarial reviews broke every heuristic: bidirectional containment let an
        untouched "Ran CI" ride on a *different* story ("...teams ran CI/CD 50% faster"); a
        4-word floor still let "Improved the release process" ride on a story containing that
        phrase; going one-directional then permanently un-covered verbose bullets. A false
        QUANTIFIED buries work the user still has to do, so coverage now UNDER-reports instead
        of lying. CQ-5b brings QUANTIFIED back, decided by a link rather than by prose.
        """
        entry = _entry(Bullet(text="Ran CI"))
        story = _story(entry, "Rebuilt releases so teams ran CI/CD 50% faster")

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


class TestFrontierIsNotYetCoverageDriven:
    """CQ-5b, deliberately NOT shipped here — see the note in ``_next_frontier``.

    Re-selecting an entry while it has uncovered bullets can trap the grill in an INFINITE
    LOOP: coverage is detected by TEXT CONTAINMENT, so a story worded differently enough to
    match no bullet leaves coverage unchanged, the frontier stays put, and the grill asks
    forever. This test pins the CURRENT (safe) behaviour so the gap is visible rather than
    silently assumed fixed.
    """

    def test_a_grilled_entry_is_still_left_behind_today(self) -> None:
        from schema import EntryStatus
        from workflows.nodes import _next_frontier

        rich = _entry(*[Bullet(text=f"line {i}") for i in range(12)]).model_copy(
            update={"status": EntryStatus.GRILLED}
        )
        other = Entry(type=ExperienceType.PROJECT, title="Side project")

        # The rich entry has 12 uncovered lines, yet the frontier moves on. That is the
        # bug CQ-5b closes; coverage is currently VISIBLE (the user can see and act on it)
        # but does not yet steer the grill.
        assert _next_frontier([rich, other], "") == str(other.entry_id)


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
