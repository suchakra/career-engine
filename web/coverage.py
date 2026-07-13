"""Grill coverage (CQ-5 / ARCHITECTURE §18, AD-18.5) — pure, no I/O.

**Coverage is the product.** The grill used to mark an entry ``GRILLED`` after ONE validated
STAR story and move the frontier on — so a user who uploaded a résumé with a dozen strong
bullets would have one of them interrogated and the other eleven silently ignored. It would
happily drill a "favourite project" while the material they actually gave us went untouched.

A bullet reaches a **terminal** state when we can say — from a FACT, never a guess — that it
has been dealt with:

- ``QUANTIFIED``   — a validated STAR story records this bullet's id in ``answers_bullet_id``:
  the grill was asking about THIS line, and a metric came back. A **link**, not a text match.
  (Honestly stated: the link records what the grill ASKED about. A user who is asked about
  "Ran CI" and answers with a metric about something else still retires that line. That is a
  far weaker failure than the text heuristic's — it needs the user to answer off-topic, and
  they can always re-open the line by editing it — but it is not omniscience, and this module
  should not pretend otherwise.)
- ``STRENGTHENED`` — reworded and the user accepted it (``source="grilled"``), or superseded by
  such a rewrite. We know, because they clicked Keep.
- ``SKIPPED``      — the user explicitly said it does not matter.

Anything else is ``UNCOVERED``, and an entry with an uncovered bullet is **not done**.

**QUANTIFIED is decided by a link because every text heuristic failed.** The obvious version —
"does a story's result text cover this bullet?" — was built, reviewed, and DELETED. A false
QUANTIFIED is the worst error this module can make: it tells the user a line is handled when it
was never grilled, silently burying the work coverage exists to surface. What broke:

- Substring containment marked an untouched "Ran CI" covered, because a *different* story in the
  same entry said "...so teams ran CI/CD 50% faster".
- A 4-word floor did not close it: "Improved the release process" still rode on "Automated
  deployments in a way that improved the release process, cutting lead time 35%".
- Making it one-directional then permanently un-covered the opposite, equally real case (a terse
  grilled result can never contain a verbose résumé line).
- Trailing punctuation — standard résumé style — defeats an exact compare outright.

The link (v2.11.0) ends the guessing, and it is what makes it SAFE for coverage to steer the
grill: every successful turn retires exactly the bullet the grill was asking about, so progress
is monotonic **by construction**. Without it, holding an entry until it is covered could loop
forever — a story worded so as to match no bullet would advance nothing.

``SKIPPED`` is the escape hatch: it lets the grill be demanding without ever being able to trap
a user on a line they never cared about.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from schema import Bullet, BulletSource, Entry, StarStory


class CoverageState(StrEnum):
    """What has become of one bullet. The first three are terminal."""

    QUANTIFIED = "quantified"
    STRENGTHENED = "strengthened"
    SKIPPED = "skipped"
    UNCOVERED = "uncovered"


_TERMINAL = frozenset(
    {CoverageState.QUANTIFIED, CoverageState.STRENGTHENED, CoverageState.SKIPPED}
)


@dataclass(frozen=True)
class EntryCoverage:
    """How much of one entry's material has actually been dealt with."""

    covered: int
    total: int
    uncovered_bullet_ids: list[str]

    @property
    def is_complete(self) -> bool:
        """True when no bullet is left in a non-terminal state."""
        return not self.uncovered_bullet_ids

    @property
    def label(self) -> str:
        """Display string — e.g. ``"7 of 12 covered"``. Empty when there is nothing to cover."""
        if self.total == 0:
            return ""
        return f"{self.covered} of {self.total} covered"


def bullet_state(
    bullet: Bullet, stories: list[StarStory], *, superseded: set[str] | None = None
) -> CoverageState:
    """Classify ONE bullet. Every state is determined by a RECORDED EVENT, never by guessing
    at prose. See the module docstring for the one honest caveat on QUANTIFIED."""
    if bullet.skipped:
        return CoverageState.SKIPPED
    if bullet.source is BulletSource.GRILLED:
        return CoverageState.STRENGTHENED
    if superseded is not None and str(bullet.bullet_id) in superseded:
        # Replaced by an accepted rewrite — the achievement survives in that bullet.
        return CoverageState.STRENGTHENED
    if any(
        s.metrics_validated and s.answers_bullet_id == str(bullet.bullet_id)
        for s in stories
    ):
        # QUANTIFIED by a LINK (v2.11.0, CQ-5b) — the grill recorded which bullet it was
        # asking about, and this story is the answer. No text comparison anywhere.
        return CoverageState.QUANTIFIED
    if bullet.derived_from_story_id and any(
        s.metrics_validated and str(s.story_id) == bullet.derived_from_story_id
        for s in stories
    ):
        # QUANTIFIED by the OTHER link (v2.12.0, CQ-6): this bullet was written to BE the
        # résumé line for a validated story — by the copywriter, or by the user overwriting
        # that line in the tailor preview. The metric is the story's; this is its prose.
        #
        # Without this, polishing a line would UN-cover it: a rewrite is stored as a new
        # bullet, no story would name it, and the entry would drop back to "needs work" —
        # so the grill would march the user back to put a number on the line they just
        # perfected. That is the CQ-5b failure exactly, and this is the gate that prevents it.
        return CoverageState.QUANTIFIED
    return CoverageState.UNCOVERED


def entry_coverage(entry: Entry, stories: list[StarStory]) -> EntryCoverage:
    """Coverage for one entry, counting only the bullets it actually still shows.

    A superseded bullet is not counted as its own line (the rewrite that replaced it is the
    one on the résumé) — counting both would make coverage unreachable: the original can
    never be quantified once it has been replaced.
    """
    superseded = {str(b.supersedes) for b in entry.bullets if b.supersedes is not None}
    live = [b for b in entry.bullets if str(b.bullet_id) not in superseded]

    uncovered = [
        str(b.bullet_id)
        for b in live
        if bullet_state(b, stories, superseded=superseded) not in _TERMINAL
    ]
    return EntryCoverage(
        covered=len(live) - len(uncovered),
        total=len(live),
        uncovered_bullet_ids=uncovered,
    )


def entry_needs_work(entry: Entry, stories: list[StarStory]) -> bool:
    """Does this entry still have UNCOVERED bullets?

    Strictly about coverage — it answers "is there supplied material we have not dealt with",
    nothing else. An entry with no bullets has nothing to cover and returns False; whether a
    bare role still needs grilling is a question about its STATUS (NEEDS_QUANTIFYING), which
    the frontier selection already handles. Conflating the two would re-open every finished
    role that happens to carry no bullets.
    """
    return not entry_coverage(entry, stories).is_complete


__all__ = [
    "CoverageState",
    "EntryCoverage",
    "bullet_state",
    "entry_coverage",
    "entry_needs_work",
]
