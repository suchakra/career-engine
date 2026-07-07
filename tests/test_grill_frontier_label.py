"""Tests for the 'currently grilling' entry label (web/grill_labels)."""

from __future__ import annotations

from schema import CareerEngineState, Entry, EntryStatus, ExperienceType
from web.grill_labels import _effective_frontier_label, _entry_label, _frontier_label


def _entry(title: str, org: str = "", status: EntryStatus = EntryStatus.NEEDS_QUANTIFYING) -> Entry:
    return Entry(type=ExperienceType.FULL_TIME, title=title, org=org, status=status)


def test_label_for_frontier_entry_includes_org() -> None:
    entry = _entry("Learning Facilitator", org="Acme")
    state = CareerEngineState(work_timeline=[entry], grill_frontier=str(entry.entry_id))
    assert _frontier_label(state) == "Learning Facilitator · Acme"


def test_label_without_org_is_just_title() -> None:
    entry = _entry("Open-source maintainer")
    state = CareerEngineState(work_timeline=[entry], grill_frontier=str(entry.entry_id))
    assert _frontier_label(state) == "Open-source maintainer"


def test_empty_when_no_frontier_set() -> None:
    assert _frontier_label(CareerEngineState(work_timeline=[_entry("X")])) == ""


def test_empty_when_frontier_not_in_timeline() -> None:
    state = CareerEngineState(work_timeline=[_entry("X")], grill_frontier="not-a-real-id")
    assert _frontier_label(state) == ""


# ── _entry_label ──────────────────────────────────────────────────────────────


def test_entry_label_title_and_org() -> None:
    assert _entry_label(_entry("Staff Engineer", org="Globex")) == "Staff Engineer · Globex"


def test_entry_label_title_only() -> None:
    assert _entry_label(_entry("Volunteer Mentor")) == "Volunteer Mentor"


def test_entry_label_none_is_empty() -> None:
    assert _entry_label(None) == ""


# ── _effective_frontier_label (BUG-2: banner on the first question after resume) ─


def test_effective_label_uses_frontier_when_set() -> None:
    entry = _entry("Learning Facilitator", org="Acme")
    state = CareerEngineState(work_timeline=[entry], grill_frontier=str(entry.entry_id))
    assert _effective_frontier_label(state) == "Learning Facilitator · Acme"


def test_effective_label_falls_back_to_next_grillable_when_frontier_blank() -> None:
    """BUG-2 regression guard: on resume the frontier can be blank (the pinned entry
    was finished/reset), yet the next turn WILL grill another entry — the banner must
    name that entry from the first question, not stay empty."""
    grilled = _entry("Perf Eng", org="Acme", status=EntryStatus.GRILLED)
    pending = _entry("Team Lead", org="Globex", status=EntryStatus.NEEDS_QUANTIFYING)
    state = CareerEngineState(work_timeline=[grilled, pending], grill_frontier="")
    assert _frontier_label(state) == ""  # the old behaviour that hid the banner
    assert _effective_frontier_label(state) == "Team Lead · Globex"


def test_effective_label_empty_when_nothing_left_to_grill() -> None:
    grilled = _entry("Perf Eng", org="Acme", status=EntryStatus.GRILLED)
    state = CareerEngineState(work_timeline=[grilled], grill_frontier="")
    assert _effective_frontier_label(state) == ""
