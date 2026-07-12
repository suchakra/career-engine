"""Portfolio view-model + injectable renderer (Phase 4B).

A read-only mirror of what the discovery loop has recorded about the user: the
``work_timeline`` as an experience list, each entry showing its status and the
STAR stories grilled out of it (linked by ``StarStory.entry_id``). Reads the
persisted ``CareerEngineState`` only — no workflow logic, no contract change.

Same two-layer, UI-logic-only pattern as :mod:`web.dashboard`:
- :func:`stories_by_entry` / :func:`build_portfolio_view` — PURE, testable
  without a Streamlit runtime.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from schema import CareerEngineState, Entry, StarStory, UserProfile

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
        bullets=[BulletCard(bullet_id=str(b.bullet_id), text=b.text) for b in entry.bullets],
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


def render_profile_section(
    view: ProfileView,
    *,
    on_save: Callable[[UserProfile], None],
    st: Any,
) -> None:
    """Render an editable Profile section inside a collapsed expander.

    Args:
        view: Display-ready profile data from :func:`build_profile_view`.
        on_save: Callback invoked with the updated :class:`~schema.UserProfile`
            whenever the user saves, adds a link, or removes a link.
        st: A Streamlit-like module (real ``streamlit`` or a test double).
    """
    with st.expander("Profile", expanded=False):
        st.subheader("Profile")

        # Row 1: name + email
        col1, col2 = st.columns(2)
        name_val = col1.text_input("Name", value=view.name, key="profile_name")
        email_val = col2.text_input("Email", value=view.email, key="profile_email")

        # Row 2: phone + location
        col3, col4 = st.columns(2)
        phone_val = col3.text_input("Phone", value=view.phone, key="profile_phone")
        location_val = col4.text_input("Location", value=view.location, key="profile_location")

        # Links list
        current_links: list[str] = list(view.links)
        if current_links:
            st.caption("Links")
        for i, link_url in enumerate(current_links):
            lc1, lc2 = st.columns([4, 1])
            lc1.write(link_url)

            def _remove(idx: int = i) -> None:
                updated = [lnk for j, lnk in enumerate(current_links) if j != idx]
                on_save(
                    UserProfile(
                        name=name_val,
                        email=email_val,
                        phone=phone_val,
                        location=location_val,
                        links=updated,
                    )
                )

            lc2.button("\u00d7 Remove", key=f"profile_remove_link_{i}", on_click=_remove)

        # Add-link row
        nc1, nc2 = st.columns([4, 1])
        new_link_val = nc1.text_input("New link", value="", key="profile_new_link")

        def _add() -> None:
            stripped = new_link_val.strip()
            if stripped:
                on_save(
                    UserProfile(
                        name=name_val,
                        email=email_val,
                        phone=phone_val,
                        location=location_val,
                        links=[*current_links, stripped],
                    )
                )

        nc2.button("Add link", key="profile_add_link", on_click=_add)

        # Save all fields
        def _save() -> None:
            on_save(
                UserProfile(
                    name=name_val,
                    email=email_val,
                    phone=phone_val,
                    location=location_val,
                    links=current_links,
                )
            )

        st.button("Save changes", key="profile_save", on_click=_save)


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
    "render_profile_section",
    "stories_by_entry",
]
