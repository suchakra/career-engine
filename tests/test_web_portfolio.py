"""Tests for the Portfolio view-model + renderer (Phase 4B / 9C).

Read-only view over the persisted discovery state. The renderer takes an injected
fake ``st``, so it is tested without a Streamlit runtime. Covers: story grouping
by entry, entry↔story attachment, the 'not grilled yet' marker, empty state, and
the editable Profile section (9C).
"""

from __future__ import annotations

from typing import Any

from schema import (
    CareerEngineState,
    Entry,
    EntryStatus,
    ExperienceType,
    StarStory,
    UserProfile,
)
from web.portfolio import (
    ProfileView,
    build_portfolio_view,
    build_profile_view,
    render_profile_section,
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
        self._issued_cols: list[FakeSt] = []

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

    def columns(self, spec: int | list[int]) -> list[FakeSt]:
        n = spec if isinstance(spec, int) else len(spec)
        cols = [FakeSt() for _ in range(n)]
        self._issued_cols.extend(cols)
        return cols

    def all_buttons(self) -> list[tuple[str, dict[str, Any]]]:
        """Buttons rendered on this st plus any it issued via columns()."""
        result = list(self.buttons)
        for col in self._issued_cols:
            result.extend(col.all_buttons())
        return result

    def expander(self, label: str, **kwargs: Any) -> FakeSt:
        return self

    def __enter__(self) -> FakeSt:
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def text_input(self, label: str, value: str = "", **kwargs: Any) -> str:
        return value


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


class _FakeCol:
    """Minimal fake Streamlit column for profile-section tests."""

    def __init__(self, presets: dict[str, str]) -> None:
        self._presets = presets
        self.writes: list[Any] = []
        self.buttons: list[tuple[str, dict[str, Any]]] = []

    def text_input(self, label: str, value: str = "", **kwargs: Any) -> str:
        return self._presets.get(label, value)

    def write(self, body: Any) -> None:
        self.writes.append(body)

    def button(self, label: str, **kwargs: Any) -> bool:
        self.buttons.append((label, kwargs))
        return False


class _FakeStProfile:
    """Fake st for render_profile_section tests; supports columns + expander."""

    def __init__(self, text_presets: dict[str, str] | None = None) -> None:
        self._presets: dict[str, str] = text_presets or {}
        self.subheaders: list[str] = []
        self.captions: list[str] = []
        self.buttons: list[tuple[str, dict[str, Any]]] = []
        self.writes: list[Any] = []
        self._cols: list[_FakeCol] = []

    # context-manager support (used by expander)
    def __enter__(self) -> _FakeStProfile:
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def expander(self, label: str, **kwargs: Any) -> _FakeStProfile:
        return self

    def subheader(self, text: str, **kwargs: Any) -> None:
        self.subheaders.append(text)

    def caption(self, text: str, **kwargs: Any) -> None:
        self.captions.append(text)

    def write(self, body: Any) -> None:
        self.writes.append(body)

    def text_input(self, label: str, value: str = "", **kwargs: Any) -> str:
        return self._presets.get(label, value)

    def columns(self, spec: int | list[int]) -> list[_FakeCol]:
        n = spec if isinstance(spec, int) else len(spec)
        cols = [_FakeCol(self._presets) for _ in range(n)]
        self._cols.extend(cols)
        return cols

    def button(self, label: str, **kwargs: Any) -> bool:
        self.buttons.append((label, kwargs))
        return False

    def all_buttons(self) -> list[tuple[str, dict[str, Any]]]:
        """Collect buttons from st itself and all columns it issued."""
        result = list(self.buttons)
        for col in self._cols:
            result.extend(col.buttons)
        return result


class TestBuildProfileView:
    """build_profile_view maps UserProfile → ProfileView (pure)."""

    def test_build_profile_view_maps_fields(self) -> None:
        profile = UserProfile(
            name="Alice",
            email="a@b.com",
            phone="123",
            location="Remote",
            links=["https://x.com"],
        )
        view = build_profile_view(profile)
        assert view.name == "Alice"
        assert view.email == "a@b.com"
        assert view.phone == "123"
        assert view.location == "Remote"
        assert view.links == ["https://x.com"]

    def test_links_is_a_copy(self) -> None:
        profile = UserProfile(links=["https://a.com"])
        view = build_profile_view(profile)
        view.links.append("https://b.com")
        assert profile.links == ["https://a.com"]


class TestRenderProfileSection:
    """render_profile_section renders widgets and fires on_save correctly."""

    def test_render_profile_section_calls_on_save(self) -> None:
        """'Save changes' on_click fires on_save with a UserProfile whose name == 'Alice'."""
        saved: list[UserProfile] = []
        fake_st = _FakeStProfile({"Name": "Alice"})
        view = ProfileView(name="", email="", phone="", location="", links=[])
        render_profile_section(view, on_save=saved.append, st=fake_st)

        save_btns = [
            (label, kw) for label, kw in fake_st.all_buttons() if label == "Save changes"
        ]
        assert len(save_btns) == 1, "Expected exactly one 'Save changes' button"
        save_btns[0][1]["on_click"]()  # simulate click
        assert len(saved) == 1
        assert saved[0].name == "Alice"

    def test_render_profile_section_empty_profile(self) -> None:
        """A ProfileView with all empty fields and links=[] renders without error."""
        fake_st = _FakeStProfile()
        view = ProfileView(name="", email="", phone="", location="", links=[])
        render_profile_section(view, on_save=lambda p: None, st=fake_st)
        assert "Profile" in fake_st.subheaders

    def test_remove_link_calls_on_save_without_removed_link(self) -> None:
        """Clicking the Remove button for a link fires on_save with that link absent."""
        saved: list[UserProfile] = []
        fake_st = _FakeStProfile()
        view = ProfileView(
            name="Bob", email="b@c.com", phone="", location="", links=["https://x.com", "https://y.com"]
        )
        render_profile_section(view, on_save=saved.append, st=fake_st)
        remove_btns = [
            (label, kw) for label, kw in fake_st.all_buttons() if label == "\u00d7 Remove"
        ]
        assert len(remove_btns) == 2
        remove_btns[0][1]["on_click"]()  # remove first link
        assert len(saved) == 1
        assert "https://x.com" not in saved[0].links
        assert "https://y.com" in saved[0].links

    def test_add_link_appends_stripped_link(self) -> None:
        """'Add link' fires on_save with new link appended (whitespace stripped)."""
        saved: list[UserProfile] = []
        fake_st = _FakeStProfile({"New link": "  https://z.com  "})
        view = ProfileView(name="", email="", phone="", location="", links=["https://a.com"])
        render_profile_section(view, on_save=saved.append, st=fake_st)

        add_btns = [
            (label, kw) for label, kw in fake_st.all_buttons() if label == "Add link"
        ]
        assert len(add_btns) == 1
        add_btns[0][1]["on_click"]()
        assert len(saved) == 1
        assert saved[0].links == ["https://a.com", "https://z.com"]

    def test_add_link_no_op_on_empty_input(self) -> None:
        """'Add link' with empty/whitespace-only input does not fire on_save."""
        saved: list[UserProfile] = []
        fake_st = _FakeStProfile({"New link": "   "})
        view = ProfileView(name="", email="", phone="", location="", links=[])
        render_profile_section(view, on_save=saved.append, st=fake_st)

        add_btns = [
            (label, kw) for label, kw in fake_st.all_buttons() if label == "Add link"
        ]
        assert len(add_btns) == 1
        add_btns[0][1]["on_click"]()
        assert len(saved) == 0, "on_save should not fire for empty/whitespace link"
