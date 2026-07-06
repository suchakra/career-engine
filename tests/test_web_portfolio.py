"""Tests for the Portfolio view-model + renderer (Phase 4B).

Read-only view over the persisted discovery state. The renderer takes an injected
fake ``st``, so it is tested without a Streamlit runtime. Covers: story grouping
by entry, entry↔story attachment, the 'not grilled yet' marker, and empty state.
"""

from __future__ import annotations

from typing import Any, ClassVar

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
        self.progress_calls: list[tuple[float, str]] = []

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

    def progress(self, value: float, text: str = "") -> None:
        self.progress_calls.append((value, text))


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

    def test_highlighted_flag_mapped(self) -> None:
        e = Entry(type=ExperienceType.FULL_TIME, title="A", org="Acme", highlighted=True)
        card = build_portfolio_view(CareerEngineState(work_timeline=[e])).entries[0]
        assert card.highlighted is True

    def test_entry_card_story_count_populated(self) -> None:
        """story_count on EntryCard reflects the number of linked StarStory objects (9K)."""
        ea, eb = _entry("A"), _entry("B")
        state = CareerEngineState(
            work_timeline=[ea, eb],
            extracted_star_stories=[
                _story(str(ea.entry_id), "cut latency 40%"),
                _story(str(ea.entry_id), "shipped feature X"),
            ],
        )
        view = build_portfolio_view(state)
        card_a = next(c for c in view.entries if c.title == "A")
        card_b = next(c for c in view.entries if c.title == "B")
        assert card_a.story_count == 2
        assert card_b.story_count == 0


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

    def test_pin_button_toggles_to_highlighted(self) -> None:
        """An unpinned entry's pin button calls on_toggle_highlight(entry_id, True) (4E)."""
        e1 = _entry("A")
        seen: list[tuple[str, bool]] = []
        st = FakeSt()
        render_portfolio(
            build_portfolio_view(CareerEngineState(work_timeline=[e1])),
            st=st,
            on_toggle_highlight=lambda eid, val: seen.append((eid, val)),
        )
        pin = [(label, kw) for label, kw in st.buttons if "Pin for tailoring" in label]
        assert len(pin) == 1
        pin[0][1]["on_click"]()
        assert seen == [(str(e1.entry_id), True)]

    def test_pinned_entry_shows_unpin_marker_and_toggles_off(self) -> None:
        e1 = Entry(type=ExperienceType.FULL_TIME, title="A", org="Acme", highlighted=True)
        seen: list[tuple[str, bool]] = []
        st = FakeSt()
        render_portfolio(
            build_portfolio_view(CareerEngineState(work_timeline=[e1])),
            st=st,
            on_toggle_highlight=lambda eid, val: seen.append((eid, val)),
        )
        assert any(s.startswith("📌") for s in st.subheaders)
        assert any("Pinned as tailoring priority" in c for c in st.captions)
        unpin = [(label, kw) for label, kw in st.buttons if label == "Unpin from tailoring priority"]
        assert len(unpin) == 1
        unpin[0][1]["on_click"]()
        assert seen == [(str(e1.entry_id), False)]

    def test_no_pin_button_without_callback(self) -> None:
        # Pass on_grill_entry so a button IS rendered — then prove the pin button
        # specifically is absent (not just that no buttons exist at all).
        st = FakeSt()
        render_portfolio(
            build_portfolio_view(CareerEngineState(work_timeline=[_entry("A")])),
            st=st,
            on_grill_entry=lambda _eid: None,
        )
        assert any(label == "Grill me about this" for label, _ in st.buttons)
        assert not any("tailoring priority" in label for label, _ in st.buttons)

    def test_progress_renders_zero_state(self) -> None:
        """EntryCard with story_count=0 renders a 'No stories recorded' caption (9K)."""
        from web.portfolio import EntryCard, PortfolioView

        card = EntryCard(
            entry_id="abc",
            title="Role A",
            org="Acme",
            dates="2022 - present",
            type_label="Full time",
            status_label="Needs quantifying",
            story_count=0,
        )
        st = FakeSt()
        render_portfolio(PortfolioView(entries=[card]), st=st)
        assert any("No stories recorded" in c for c in st.captions)
        assert st.progress_calls == []

    def test_progress_renders_partial(self) -> None:
        """EntryCard with story_count=2/3 calls st.progress with fraction in (0, 1) (9K)."""
        from web.portfolio import EntryCard, PortfolioView

        card = EntryCard(
            entry_id="abc",
            title="Role A",
            org="Acme",
            dates="2022 - present",
            type_label="Full time",
            status_label="Needs quantifying",
            story_count=2,
            stories_target=3,
        )
        st = FakeSt()
        render_portfolio(PortfolioView(entries=[card]), st=st)
        assert len(st.progress_calls) == 1
        fraction, text = st.progress_calls[0]
        assert 0.0 < fraction < 1.0
        assert "2 stories recorded" in text
        assert "✓" not in text

    def test_progress_renders_complete(self) -> None:
        """EntryCard with story_count >= stories_target calls st.progress with 1.0 and '✓' (9K)."""
        from web.portfolio import EntryCard, PortfolioView

        card = EntryCard(
            entry_id="abc",
            title="Role A",
            org="Acme",
            dates="2022 - present",
            type_label="Full time",
            status_label="Needs quantifying",
            story_count=3,
            stories_target=3,
        )
        st = FakeSt()
        render_portfolio(PortfolioView(entries=[card]), st=st)
        assert len(st.progress_calls) == 1
        fraction, text = st.progress_calls[0]
        assert fraction == 1.0
        assert "✓" in text


# ---------------------------------------------------------------------------
# Integration-level ordering test (9B)
# ---------------------------------------------------------------------------


def test_add_experience_cta_precedes_entry_list(monkeypatch: Any) -> None:
    """The 'Add' CTA caption and expander appear BEFORE entry subheaders (9B).

    _render_portfolio now calls _render_add_experience_form first, then
    render_portfolio, so the CTA must land earlier in the widget stream than
    any entry title rendered by the portfolio view.
    """
    import web.streamlit_app as streamlit_app

    log: list[tuple[str, str]] = []

    class _Ctx:
        """Minimal context manager that silently absorbs nested attribute calls."""

        def __enter__(self) -> _Ctx:
            return self

        def __exit__(self, *args: Any) -> None:
            pass

        def __getattr__(self, name: str) -> Any:
            return lambda *a, **kw: None

    class _RecordingSt:
        """Fake st that logs caption/subheader/expander/title calls in order."""

        session_state: ClassVar[dict[str, Any]] = {}

        def caption(self, body: str, **kw: Any) -> None:
            log.append(("caption", body))

        def subheader(self, body: str, **kw: Any) -> None:
            log.append(("subheader", body))

        def title(self, body: str, **kw: Any) -> None:
            log.append(("title", body))

        def expander(self, label: str, **kw: Any) -> _Ctx:
            log.append(("expander", label))
            return _Ctx()

        def form(self, *args: Any, **kw: Any) -> _Ctx:
            return _Ctx()

        def info(self, *args: Any, **kw: Any) -> None:
            pass

        def divider(self, **kw: Any) -> None:
            pass

        def write(self, *args: Any, **kw: Any) -> None:
            pass

        def button(self, *args: Any, **kw: Any) -> bool:
            return False

        def text_input(self, *args: Any, **kw: Any) -> str:
            return ""

        def text_area(self, *args: Any, **kw: Any) -> str:
            return ""

        def selectbox(self, label: str, options: Any, index: int = 0, **kw: Any) -> Any:
            return list(options)[index]

        def form_submit_button(self, *args: Any, **kw: Any) -> bool:
            return False

        def __getattr__(self, name: str) -> Any:
            return lambda *a, **kw: None

    fake_st = _RecordingSt()

    entry = Entry(type=ExperienceType.FULL_TIME, title="Staff Engineer", org="Acme")
    state = CareerEngineState(work_timeline=[entry])

    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(
        streamlit_app, "_load_discovery_state", lambda *, user_id, today: state
    )
    monkeypatch.setattr(
        streamlit_app, "_render_master_resume_download", lambda *, user_id, state: None
    )
    monkeypatch.setattr(
        streamlit_app, "_jump_grill_to_entry", lambda *, user_id, entry_id: None
    )
    monkeypatch.setattr(
        streamlit_app,
        "_set_entry_highlight",
        lambda *, user_id, entry_id, highlighted: None,
    )

    streamlit_app._render_portfolio(user_id="u1", today="2026-07-06")

    cta_idx = next(
        (i for i, (kind, val) in enumerate(log) if "Add a role" in val),
        None,
    )
    entry_idx = next(
        (i for i, (kind, val) in enumerate(log) if kind == "subheader" and "Staff Engineer" in val),
        None,
    )

    assert cta_idx is not None, f"CTA caption not found in log; log={log}"
    assert entry_idx is not None, f"Entry subheader not found in log; log={log}"
    assert cta_idx < entry_idx, (
        f"CTA (pos {cta_idx}) must precede entry subheader (pos {entry_idx}); log={log}"
    )
