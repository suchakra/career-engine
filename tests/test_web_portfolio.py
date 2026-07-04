"""Tests for the Portfolio view-model + renderer (Phase 4B).

Read-only view over the persisted discovery state. The renderer takes an injected
fake ``st``, so it is tested without a Streamlit runtime. Covers: story grouping
by entry, entry↔story attachment, the 'not grilled yet' marker, and empty state.
"""

from __future__ import annotations

from typing import Any

from schema import CareerEngineState, Entry, EntryStatus, ExperienceType, StarStory
from web.portfolio import (
    build_portfolio_view,
    render_portfolio,
    stories_by_entry,
)


class FakeSt:
    """Records portfolio render calls for assertions."""

    def __init__(self) -> None:
        self.titles: list[str] = []
        self.captions: list[str] = []
        self.subheaders: list[str] = []
        self.writes: list[Any] = []
        self.infos: list[str] = []
        self.dividers = 0
        self.buttons: list[tuple[str, dict[str, Any]]] = []

    def title(self, body: str) -> None:
        self.titles.append(body)

    def caption(self, body: str) -> None:
        self.captions.append(body)

    def subheader(self, body: str) -> None:
        self.subheaders.append(body)

    def write(self, body: Any) -> None:
        self.writes.append(body)

    def info(self, body: str) -> None:
        self.infos.append(body)

    def divider(self) -> None:
        self.dividers += 1

    def button(self, label: str, **kwargs: Any) -> None:
        self.buttons.append((label, kwargs))


def _entry(title: str, status: EntryStatus = EntryStatus.NEEDS_QUANTIFYING) -> Entry:
    return Entry(
        type=ExperienceType.FULL_TIME,
        title=title,
        org="Acme",
        start_date="2022",
        end_date="",
        status=status,
    )


def _story(entry_id: str, result: str, validated: bool = True) -> StarStory:
    return StarStory(
        entry_id=entry_id,
        pillar="delivery",
        situation="context",
        result=result,
        metrics_validated=validated,
    )


class TestStoriesByEntry:
    """stories_by_entry groups stories by their entry_id string."""

    def test_groups_by_entry_id(self) -> None:
        e1, e2 = _entry("A"), _entry("B")
        state = CareerEngineState(
            work_timeline=[e1, e2],
            extracted_star_stories=[
                _story(str(e1.entry_id), "cut latency 40%"),
                _story(str(e1.entry_id), "shipped X"),
                _story(str(e2.entry_id), "led team of 5"),
            ],
        )
        grouped = stories_by_entry(state)
        assert len(grouped[str(e1.entry_id)]) == 2
        assert len(grouped[str(e2.entry_id)]) == 1

    def test_no_stories_yields_empty_map(self) -> None:
        assert stories_by_entry(CareerEngineState()) == {}

    def test_unknown_entry_id_grouped_under_empty_string(self) -> None:
        """A story with no entry_id groups under '' and attaches to no timeline entry."""
        e1 = _entry("A")
        state = CareerEngineState(
            work_timeline=[e1],
            extracted_star_stories=[_story("", "orphan achievement")],
        )
        grouped = stories_by_entry(state)
        assert [s.result for s in grouped[""]] == ["orphan achievement"]
        # The orphan does not attach to the real entry.
        assert build_portfolio_view(state).entries[0].not_grilled_yet is True


class TestBuildPortfolioView:
    """build_portfolio_view attaches the right stories to each entry."""

    def test_attaches_stories_to_correct_entry(self) -> None:
        e1, e2 = _entry("A"), _entry("B")
        state = CareerEngineState(
            work_timeline=[e1, e2],
            extracted_star_stories=[_story(str(e1.entry_id), "cut latency 40%")],
        )
        view = build_portfolio_view(state)
        assert [c.title for c in view.entries] == ["A", "B"]  # preserves order
        card1, card2 = view.entries
        assert card1.stories[0].result == "cut latency 40%"
        assert card1.not_grilled_yet is False
        assert card2.not_grilled_yet is True  # no stories linked

    def test_entry_metadata_mapped(self) -> None:
        state = CareerEngineState(work_timeline=[_entry("A", EntryStatus.GRILLED)])
        card = build_portfolio_view(state).entries[0]
        assert card.org == "Acme"
        assert card.dates == "2022 - present"
        assert card.type_label == "Full time"
        assert card.status_label == "Grilled"

    def test_empty_state(self) -> None:
        view = build_portfolio_view(CareerEngineState())
        assert view.is_empty is True
        assert view.entries == []


class TestRenderPortfolio:
    """render_portfolio maps the view to widgets via an injected fake st."""

    def test_empty_state_renders_info_not_entries(self) -> None:
        st = FakeSt()
        render_portfolio(build_portfolio_view(CareerEngineState()), st=st)
        assert st.infos  # empty-state info shown
        assert st.subheaders == []

    def test_entries_and_story_results_rendered(self) -> None:
        e1 = _entry("Senior Engineer", EntryStatus.GRILLED)
        state = CareerEngineState(
            work_timeline=[e1],
            extracted_star_stories=[_story(str(e1.entry_id), "cut latency 40%")],
        )
        st = FakeSt()
        render_portfolio(build_portfolio_view(state), st=st)
        assert "Senior Engineer" in st.subheaders
        assert any("cut latency 40%" in str(w) for w in st.writes)

    def test_not_grilled_marker_rendered_for_bare_entry(self) -> None:
        st = FakeSt()
        render_portfolio(build_portfolio_view(CareerEngineState(work_timeline=[_entry("A")])), st=st)
        assert any("Not grilled yet" in str(w) for w in st.writes)

    def test_existing_bullets_rendered(self) -> None:
        """An entry's existing resume bullets are shown in the Portfolio view."""
        entry = Entry(
            type=ExperienceType.FULL_TIME,
            title="A",
            org="Acme",
            bullets=["Built the thing", "Owned the roadmap"],
        )
        st = FakeSt()
        render_portfolio(build_portfolio_view(CareerEngineState(work_timeline=[entry])), st=st)
        assert any("Built the thing" in str(w) for w in st.writes)

    def test_grill_me_button_invokes_callback_with_entry_id(self) -> None:
        """The 'Grill me about this' button calls on_grill_entry with the entry_id (4C)."""
        e1 = _entry("A")
        state = CareerEngineState(work_timeline=[e1])
        seen: list[str] = []
        st = FakeSt()
        render_portfolio(
            build_portfolio_view(state), st=st, on_grill_entry=lambda eid: seen.append(eid)
        )
        grill_buttons = [(label, kw) for label, kw in st.buttons if label == "Grill me about this"]
        assert len(grill_buttons) == 1
        grill_buttons[0][1]["on_click"]()  # simulate the click
        assert seen == [str(e1.entry_id)]

    def test_no_grill_button_without_callback(self) -> None:
        """Without on_grill_entry, no steering button is rendered (pure read view)."""
        st = FakeSt()
        render_portfolio(build_portfolio_view(CareerEngineState(work_timeline=[_entry("A")])), st=st)
        assert st.buttons == []
