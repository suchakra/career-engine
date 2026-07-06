"""Portfolio view-model + injectable renderer (Phase 4B).

A read-only mirror of what the discovery loop has recorded about the user: the
``work_timeline`` as an experience list, each entry showing its status and the
STAR stories grilled out of it (linked by ``StarStory.entry_id``). Reads the
persisted ``CareerEngineState`` only — no workflow logic, no contract change.

Same two-layer, UI-logic-only pattern as :mod:`web.dashboard`:
- :func:`stories_by_entry` / :func:`build_portfolio_view` — PURE, testable
  without a Streamlit runtime.
- :func:`render_portfolio` — thin map from view-model → widgets via an injected
  ``st``-like module.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from schema import CareerEngineState, Entry, StarStory

_EMPTY_TEXT = (
    "Nothing recorded yet. Start a **Grill** and your experiences — and the "
    "achievements grilled out of them — will show up here."
)
_NOT_GRILLED_TEXT = "Not grilled yet — start a grill to capture achievements here."


@dataclass(frozen=True)
class StoryCard:
    """One recorded STAR story, display-ready."""

    situation: str
    task: str
    action: str
    result: str
    metric_validated: bool


@dataclass(frozen=True)
class EntryCard:
    """One experience entry with its recorded stories, display-ready."""

    entry_id: str
    title: str
    org: str
    dates: str
    type_label: str
    status_label: str
    bullets: list[str] = field(default_factory=list)
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


def _entry_card(entry: Entry, stories: list[StarStory]) -> EntryCard:
    """Map one Entry + its stories into a display-ready EntryCard."""
    return EntryCard(
        entry_id=str(entry.entry_id),
        title=entry.title,
        org=entry.org,
        dates=_dates(entry),
        type_label=_label(str(entry.type.value)),
        status_label=_label(str(entry.status.value)),
        bullets=list(entry.bullets),
        stories=[
            StoryCard(
                situation=s.situation,
                task=s.task,
                action=s.action,
                result=s.result,
                metric_validated=s.metrics_validated,
            )
            for s in stories
        ],
        highlighted=entry.highlighted,
        story_count=len(stories),
    )


def build_portfolio_view(state: CareerEngineState) -> PortfolioView:
    """Build the portfolio view-model from the discovery session state (pure).

    Preserves ``work_timeline`` order (newest-first by convention) and attaches
    each entry's linked stories via :func:`stories_by_entry`.
    """
    grouped = stories_by_entry(state)
    entries = [_entry_card(entry, grouped.get(str(entry.entry_id), [])) for entry in state.work_timeline]
    return PortfolioView(entries=entries)


def render_portfolio(
    view: PortfolioView,
    *,
    st: Any,
    on_grill_entry: Callable[[str], None] | None = None,
    on_toggle_highlight: Callable[[str, bool], None] | None = None,
) -> None:
    """Render the portfolio via an injected ``st``-like module (thin pass-through).

    Args:
        view: The view-model from :func:`build_portfolio_view`.
        st: A Streamlit-like module (real ``streamlit`` in the app; a fake in tests).
        on_grill_entry: Optional callback wired to each entry's "Grill me about
            this" button; receives the entry_id. The backend frontier-write +
            view switch live in the caller (``streamlit_app``), keeping this
            renderer free of persistence logic (4C).
        on_toggle_highlight: Optional callback for the pin control (4E); receives
            ``(entry_id, new_highlighted)``. The persistence lives in the caller.
    """
    st.title("Your portfolio")

    if view.is_empty:
        st.info(view.empty_text)
        return

    st.caption(
        "Everything recorded about you, by experience. Pin the ones you want the "
        "Tailor to always prioritize."
    )
    for entry in view.entries:
        st.divider()
        pin = "📌 " if entry.highlighted else ""
        st.subheader(f"{pin}{entry.title or '(untitled experience)'}")
        meta = " · ".join(p for p in (entry.org, entry.dates, entry.type_label) if p)
        if meta:
            st.caption(meta)
        st.caption(f"Status: {entry.status_label}")
        if entry.highlighted:
            st.caption("⭐ Pinned as tailoring priority — always included when tailoring.")

        if entry.story_count == 0:
            st.caption("No stories yet — click 'Grill me about this' to start.")
        else:
            st.progress(
                min(entry.story_count / entry.stories_target, 1.0),
                text=(
                    f"{entry.story_count} stor{'y' if entry.story_count == 1 else 'ies'} recorded"
                    + (" ✓" if entry.story_count >= entry.stories_target else "")
                ),
            )

        # Existing resume bullets/notes for this entry (may be present even before
        # any grilling has produced STAR stories).
        if entry.bullets:
            st.caption("From your resume:")
            for bullet in entry.bullets:
                st.write(f"• {bullet}")

        if entry.not_grilled_yet:
            st.write(f"_{_NOT_GRILLED_TEXT}_")
        else:
            st.caption("Recorded achievements:")
            for story in entry.stories:
                check = "✅" if story.metric_validated else "•"
                st.write(f"{check} {story.result}")
                # Supporting context (we deliberately never surface the STAR labels
                # to the user — see StarStory docstring), one line per present field.
                for context in (story.situation, story.task, story.action):
                    if context:
                        st.caption(context)

        # Steer the grill onto this specific experience (4C).
        if on_grill_entry is not None:
            st.button(
                "Grill me about this",
                key=f"grill_entry_{entry.entry_id}",
                on_click=lambda eid=entry.entry_id: on_grill_entry(eid),
            )

        # Pin/unpin this experience as a tailoring priority (4E).
        if on_toggle_highlight is not None:
            label = "Unpin from tailoring priority" if entry.highlighted else "📌 Pin for tailoring priority"
            st.button(
                label,
                key=f"pin_entry_{entry.entry_id}",
                on_click=lambda eid=entry.entry_id, val=not entry.highlighted: on_toggle_highlight(
                    eid, val
                ),
            )


__all__ = [
    "EntryCard",
    "PortfolioView",
    "StoryCard",
    "build_portfolio_view",
    "render_portfolio",
    "stories_by_entry",
]
