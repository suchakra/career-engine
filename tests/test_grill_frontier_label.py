"""Tests for the 'currently grilling' entry label (web/grill_ui._frontier_label)."""

from __future__ import annotations

from schema import CareerEngineState, Entry, ExperienceType
from web.grill_ui import _frontier_label


def _entry(title: str, org: str = "") -> Entry:
    return Entry(type=ExperienceType.FULL_TIME, title=title, org=org)


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
