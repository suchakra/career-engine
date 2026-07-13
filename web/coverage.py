"""Grill coverage (CQ-5 / ARCHITECTURE §18, AD-18.5) — pure, no I/O.

**Coverage is the product.** The grill used to mark an entry ``GRILLED`` after ONE validated
STAR story and move the frontier on — so a user who uploaded a résumé with a dozen strong
bullets would have one of them interrogated and the other eleven silently ignored. It would
happily drill a "favourite project" while the material they actually gave us went untouched.

A bullet reaches a **terminal** state when we can say, RELIABLY, that it has been dealt with:

- ``STRENGTHENED`` — reworded and the user accepted it (``source="grilled"``), or superseded
  by such a rewrite. Deterministic: we know, because they clicked Keep.
- ``SKIPPED``      — the user explicitly said it does not matter. Deterministic.

Anything else is ``UNCOVERED``.

**There is deliberately no QUANTIFIED state yet.** The obvious one — "a validated STAR story's
result text covers this bullet" — was implemented and then REMOVED, because text matching
cannot decide it and a wrong answer here is the worst thing this module can do: a false
QUANTIFIED tells the user a line is handled when it was never grilled, silently burying the
work that coverage exists to surface. Two adversarial reviews demolished every heuristic tried:

- Bidirectional substring containment marked an untouched "Ran CI" as covered because a
  *different* story in the same entry said "...so teams ran CI/CD 50% faster".
- A minimum-length floor did not close it either: "Improved the release process" (4 words) still
  rode on "Automated deployments in a way that improved the release process, cutting lead 35%".
- Making it one-directional then permanently un-covered the opposite, equally real case (a
  terse grilled result can never contain a verbose résumé line).
- Trailing punctuation — standard résumé style — defeats an exact compare outright.

So coverage under-reports rather than lies: an UNCOVERED bullet may in fact have been grilled.
That is the honest failure direction, and Skip is always available. **CQ-5b** adds the real fix
— the grill recording WHICH bullet a story answers — and QUANTIFIED returns with it, decided by
a link rather than by guessing at prose.

``SKIPPED`` is the escape hatch: it is what will let the grill (once CQ-5b steers it) insist on
coverage without being able to trap a user on a line they never cared about.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from schema import Bullet, BulletSource, Entry, StarStory


class CoverageState(StrEnum):
    """What has become of one bullet. The first two are terminal."""

    STRENGTHENED = "strengthened"
    SKIPPED = "skipped"
    UNCOVERED = "uncovered"


_TERMINAL = frozenset({CoverageState.STRENGTHENED, CoverageState.SKIPPED})


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
    """Classify ONE bullet. Only states we can determine RELIABLY are reported.

    ``stories`` is accepted (and currently unused) so the signature is ready for CQ-5b, which
    adds the story→bullet link that makes a trustworthy QUANTIFIED possible.
    """
    if bullet.skipped:
        return CoverageState.SKIPPED
    if bullet.source is BulletSource.GRILLED:
        return CoverageState.STRENGTHENED
    if superseded is not None and str(bullet.bullet_id) in superseded:
        # Replaced by an accepted rewrite — the achievement survives in that bullet.
        return CoverageState.STRENGTHENED
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
