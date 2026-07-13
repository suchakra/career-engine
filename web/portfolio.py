"""Portfolio view-model builders (Phase 4B; the Streamlit renderers went with the cutover).

A read-only mirror of what the discovery loop has recorded about the user: the
``work_timeline`` as an experience list, each entry showing its status and the
STAR stories grilled out of it (linked by ``StarStory.entry_id``). Reads the
persisted ``CareerEngineState`` only — no workflow logic, no contract change.

Pure view-model builders only (:func:`stories_by_entry` / :func:`build_portfolio_view` /
:func:`build_profile_view`): they read state and return display-ready dataclasses. There is
no rendering layer left in this module — the Streamlit renderers that used to pair with them
went out with the rest of Streamlit, and the Next.js client consumes these view models over
the API instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from schema import CareerEngineState, Entry, StarStory, UserProfile
from web.coverage import bullet_state, entry_coverage

_EMPTY_TEXT = (
    "Nothing recorded yet. Start a **Grill** and your experiences — and the "
    "achievements grilled out of them — will show up here."
)
_NOT_GRILLED_TEXT = "Not grilled yet — start a grill to capture achievements here."


@dataclass
class ProfileView:
    """Display-ready user profile (fully testable without Streamlit)."""

    name: str
    email: str
    phone: str
    location: str
    links: list[str]


@dataclass(frozen=True)
class StoryCard:
    """One recorded STAR story, display-ready."""

    situation: str
    task: str
    action: str
    result: str
    metric_validated: bool
    story_id: str = ""


@dataclass(frozen=True)
class BulletCard:
    """One experience bullet, display-ready — carries its ID so the UI can address it.

    The UI used to edit bullets by array INDEX, which shifts under any concurrent insert
    or delete. Since v2.9.0 a bullet has a stable ``bullet_id`` (AD-18.3); the view hands
    it to the client so edits and deletes name the line they mean.
    """

    bullet_id: str
    text: str
    state: str = "uncovered"
    """Coverage state (CQ-5): quantified | strengthened | skipped | uncovered."""


@dataclass(frozen=True)
class EntryCard:
    """One experience entry with its recorded stories, display-ready."""

    entry_id: str
    title: str
    org: str
    dates: str
    type_label: str
    status_label: str
    bullets: list[BulletCard] = field(default_factory=list)
    coverage_label: str = ""
    """e.g. "7 of 12 covered" — so the user knows what is LEFT rather than guessing (CQ-5)."""
    is_covered: bool = True
    stories: list[StoryCard] = field(default_factory=list)
    highlighted: bool = False
    story_count: int = 0
    stories_target: int = 3

    @property
    def not_grilled_yet(self) -> bool:
        """True when no STAR stories are linked to this entry yet."""
        return not self.stories


@dataclass(frozen=True)
class PortfolioView:
    """Display-ready portfolio state (fully testable without Streamlit)."""

    entries: list[EntryCard]
    empty_text: str = _EMPTY_TEXT

    @property
    def is_empty(self) -> bool:
        """True when the timeline has no entries."""
        return not self.entries


def stories_by_entry(state: CareerEngineState) -> dict[str, list[StarStory]]:
    """Group the session's STAR stories by their ``entry_id`` (string keys).

    Stories with an empty/unknown ``entry_id`` are grouped under the empty string
    (they simply won't attach to any timeline entry). Pure — no I/O.
    """
    grouped: dict[str, list[StarStory]] = {}
    for story in state.extracted_star_stories:
        grouped.setdefault(story.entry_id, []).append(story)
    return grouped


def _dates(entry: Entry) -> str:
    """Human date range: 'YYYY - present', 'YYYY - YYYY', or '' if both unknown."""
    if not entry.start_date and not entry.end_date:
        return ""
    start = entry.start_date or "?"
    end = entry.end_date or "present"
    return f"{start} - {end}"


def _label(value: str) -> str:
    """'full_time' -> 'Full time' (enum value → readable label)."""
    return value.replace("_", " ").capitalize()


def _superseded(entry: Entry) -> set[str]:
    """Bullet ids replaced by an accepted rewrite — they no longer show as their own line."""
    return {str(b.supersedes) for b in entry.bullets if b.supersedes is not None}


def _entry_card(entry: Entry, stories: list[StarStory]) -> EntryCard:
    """Map one Entry + its stories into a display-ready EntryCard."""
    superseded = _superseded(entry)
    coverage = entry_coverage(entry, stories)
    return EntryCard(
        entry_id=str(entry.entry_id),
        title=entry.title,
        org=entry.org,
        dates=_dates(entry),
        type_label=_label(str(entry.type.value)),
        status_label=_label(str(entry.status.value)),
        bullets=[
            BulletCard(
                bullet_id=str(b.bullet_id),
                text=b.text,
                state=str(bullet_state(b, stories, superseded=superseded).value),
            )
            for b in entry.bullets
            if str(b.bullet_id) not in superseded
        ],
        coverage_label=coverage.label,
        is_covered=coverage.is_complete,
        stories=[
            StoryCard(
                situation=s.situation,
                task=s.task,
                action=s.action,
                result=s.result,
                metric_validated=s.metrics_validated,
                story_id=str(s.story_id),
            )
            for s in stories
        ],
        highlighted=entry.highlighted,
        story_count=len(stories),
    )


def build_profile_view(profile: UserProfile) -> ProfileView:
    """Map a UserProfile into a display-ready ProfileView (pure)."""
    return ProfileView(
        name=profile.name,
        email=profile.email,
        phone=profile.phone,
        location=profile.location,
        links=list(profile.links),
    )


def build_portfolio_view(state: CareerEngineState) -> PortfolioView:
    """Build the portfolio view-model from the discovery session state (pure).

    Preserves ``work_timeline`` order (newest-first by convention) and attaches
    each entry's linked stories via :func:`stories_by_entry`.
    """
    grouped = stories_by_entry(state)
    entries = [_entry_card(entry, grouped.get(str(entry.entry_id), [])) for entry in state.work_timeline]
    return PortfolioView(entries=entries)


__all__ = [
    "EntryCard",
    "PortfolioView",
    "ProfileView",
    "StoryCard",
    "build_portfolio_view",
    "build_profile_view",
    "stories_by_entry",
]
