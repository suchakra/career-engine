"""Tests for the web Tailor flow (web/tailor.py)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import cast

import pytest

import workflows.nodes as nodes
from integration.model_client import GeminiModelClient
from schema import CareerEngineState, Entry, EntryStatus, ExperienceType, StarStory
from tests.test_integration import ScriptedNodeClient
from web.tailor import (
    build_tailored_resume_json,
    parse_tailored,
    tailored_to_markdown,
)

_TAILORED = {
    "tailored_summary": "Delivery-focused engineer who cut latency and cost.",
    "selected_achievements": [
        {
            "pillar": "performance",
            "headline": "Cut p99 latency 85% across 40 services",
            "full_text": "Led a caching + query overhaul.",
            "relevance_note": "The JD stresses low-latency systems.",
        }
    ],
}


@pytest.fixture(autouse=True)
def _restore_factory() -> Iterator[None]:
    original = nodes._client_factory
    yield
    nodes._client_factory = original


class TestParseTailored:
    def test_parses_summary_and_achievements(self) -> None:
        tr = parse_tailored(json.dumps(_TAILORED))
        assert tr.summary.startswith("Delivery-focused")
        assert len(tr.achievements) == 1
        assert tr.achievements[0].headline.startswith("Cut p99")
        assert tr.is_empty is False

    def test_handles_markdown_fenced_json(self) -> None:
        tr = parse_tailored("```json\n" + json.dumps(_TAILORED) + "\n```")
        assert len(tr.achievements) == 1

    def test_unparseable_yields_empty(self) -> None:
        tr = parse_tailored("sorry, I can't do that")
        assert tr.is_empty is True

    def test_achievement_without_headline_skipped(self) -> None:
        payload = {"tailored_summary": "s", "selected_achievements": [{"full_text": "x"}]}
        assert parse_tailored(json.dumps(payload)).achievements == []


class TestTailoredToMarkdown:
    def test_renders_headings_and_bullets(self) -> None:
        md = tailored_to_markdown(parse_tailored(json.dumps(_TAILORED)))
        assert "# Tailored résumé" in md
        assert "Delivery-focused" in md
        assert "**Cut p99 latency 85% across 40 services**" in md
        assert "Why it fits" in md


class TestBuildTailoredResumeJson:
    def test_finalizes_then_tailors_from_stories(self) -> None:
        """With no master résumé, it assembles one from stories, then tailors."""
        client = ScriptedNodeClient(
            responses={
                "assembling a master resume": json.dumps(
                    {"summary": "Master.", "achievements_by_pillar": {}}
                ),
                "tailoring a master resume": json.dumps(_TAILORED),
            }
        )
        entry = Entry(type=ExperienceType.FULL_TIME, title="Eng", status=EntryStatus.GRILLED)
        state = CareerEngineState(
            work_timeline=[entry],
            extracted_star_stories=[
                StarStory(
                    entry_id=str(entry.entry_id),
                    pillar="performance",
                    result="cut latency 85%",
                    metrics_validated=True,
                )
            ],
        )
        out = build_tailored_resume_json(
            state, "We need a low-latency systems engineer.", client=cast(GeminiModelClient, client)
        )
        assert parse_tailored(out).achievements[0].headline.startswith("Cut p99")
