"""Grill coverage (CQ-5 / ARCHITECTURE §18, AD-18.5) — pure, no I/O.

**Coverage is the product.** The grill used to mark an entry ``GRILLED`` after ONE validated
STAR story and move the frontier on — so a user who uploaded a résumé with a dozen strong
bullets would have one of them interrogated and the other eleven silently ignored. It would
happily drill a "favourite project" while the material they actually gave us went untouched.

Every supplied bullet must reach one of three **terminal** states:

- ``QUANTIFIED``   — a validated STAR story covers it (we got a metric out of it).
- ``STRENGTHENED`` — it was reworded and the user accepted it (``source="grilled"``), or it
  was superseded by such a rewrite.
- ``SKIPPED``      — the user explicitly said it does not matter.

Anything else is ``UNCOVERED``, and an entry with an uncovered bullet is **not done**.

``SKIPPED`` is not a nicety: it is the escape hatch. Without it, insisting on coverage could
trap a user in an endless grill over a line they never cared about. With it, the grill can be
demanding *and* always leave them a way out.
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


_MIN_TOKENS_FOR_CONTAINMENT = 4
"""A bullet must be this substantial before substring containment is trusted.

Short, generic lines ("Ran CI", "Led hiring", "Python") turn up as substrings of unrelated
prose all the time. Without this floor, an entry's OTHER story ("...ran CI/CD pipelines 50%
faster...") silently marks an untouched "Ran CI" bullet as QUANTIFIED — telling the user a line
is covered when it was never grilled. A false QUANTIFIED is the worst error this module can
make: it HIDES outstanding work, which is the very thing coverage exists to surface.
"""


def _covers(story_result: str, bullet_text: str) -> bool:
    """Does a validated story's result already account for this bullet?

    Exact match always counts. Substring containment only counts for a bullet substantial
    enough (>= ``_MIN_TOKENS_FOR_CONTAINMENT`` words) that an accidental match is implausible.

    This is deliberately biased toward UNDER-reporting coverage: a false UNCOVERED merely asks
    the user about something already handled (annoying, recoverable), while a false QUANTIFIED
    hides work they still need to do (silent, and the opposite of this module's purpose).

    Text matching is a stopgap. **CQ-5b** replaces it with a real link — the grill recording
    WHICH bullet a story answers — at which point this heuristic goes away entirely.
    """
    a = " ".join(story_result.split()).casefold()
    b = " ".join(bullet_text.split()).casefold()
    if not a or not b:
        return False
    if a == b:
        return True
    if len(b.split()) < _MIN_TOKENS_FOR_CONTAINMENT:
        return False  # too short to trust a substring hit
    return b in a


def bullet_state(
    bullet: Bullet, stories: list[StarStory], *, superseded: set[str] | None = None
) -> CoverageState:
    """Classify ONE bullet. See the module docstring for what each state means."""
    if bullet.skipped:
        return CoverageState.SKIPPED
    if bullet.source is BulletSource.GRILLED:
        return CoverageState.STRENGTHENED
    if superseded is not None and str(bullet.bullet_id) in superseded:
        # It was replaced by an accepted rewrite — the achievement survives in that bullet.
        return CoverageState.STRENGTHENED
    if any(
        s.metrics_validated and _covers(s.result, bullet.text) for s in stories
    ):
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
