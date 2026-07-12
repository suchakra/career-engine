"""Tests for the résumé copywriter (web/copywriter.py — CQ-4, ARCHITECTURE §18).

Model-free: everything except ``copywrite_entry`` is pure, and that one is exercised with a
scripted client. The guarantees under test are the ones that protect the user's résumé:

- The prompt carries the FULL S/T/A/R, not just the result — the whole reason this stage
  exists is that we were collecting situation/task/action and throwing them away at render.
- A bullet already covered by a story is not sent twice (one achievement → one proposal).
- A proposal naming a ``source_id`` we never sent is DROPPED — the model must not attach a
  line to nothing.
- A malformed response proposes NOTHING rather than raising: copywriting is an improvement,
  never a dependency, and must not be able to take the résumé down with it.
- Accepting a rewrite SUPERSEDES the original by id, so the résumé cannot show both.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from schema import Bullet, BulletSource, Entry, ExperienceType, StarStory
from web.copywriter import (
    Proposal,
    accept,
    build_prompt,
    copywrite_entry,
    parse_proposals,
)


def _entry(*texts: str) -> Entry:
    return Entry(
        type=ExperienceType.FULL_TIME,
        title="Staff Engineer",
        org="Texada",
        bullets=[Bullet(text=t) for t in texts],
    )


def _story(entry: Entry, **kw: str) -> StarStory:
    return StarStory(
        entry_id=str(entry.entry_id),
        pillar="delivery",
        situation=kw.get("situation", ""),
        task=kw.get("task", ""),
        action=kw.get("action", ""),
        result=kw.get("result", ""),
        metrics_validated=True,
    )


class TestPrompt:
    def test_the_prompt_carries_the_full_STAR_not_just_the_result(self) -> None:
        """The bug this whole stage exists to fix: S, T and A were being discarded."""
        entry = _entry()
        story = _story(
            entry,
            situation="Deploys failed weekly",
            task="Stabilise the pipeline",
            action="Rebuilt CI on Kubernetes",
            result="Cut deploy failures 40%",
        )

        prompt = build_prompt(entry, [story])

        for fragment in (
            "Deploys failed weekly",
            "Stabilise the pipeline",
            "Rebuilt CI on Kubernetes",
            "Cut deploy failures 40%",
        ):
            assert fragment in prompt
        assert "Staff Engineer" in prompt and "Texada" in prompt

    def test_a_bullet_already_covered_by_a_story_is_not_sent_twice(self) -> None:
        """One achievement must yield ONE proposal, not two competing rewrites."""
        entry = _entry("Rebuilt CI", "Hired six engineers")
        story = _story(entry, action="x", result="Rebuilt CI, cutting failures 40%")

        prompt = build_prompt(entry, [story])
        items = json.loads(prompt.split("MATERIAL:\n", 1)[1])

        assert len(items) == 2  # the story + the UNCOVERED bullet
        assert any(i.get("existing_bullet") == "Hired six engineers" for i in items)
        assert not any(i.get("existing_bullet") == "Rebuilt CI" for i in items)

    def test_an_entry_with_no_material_produces_no_call(self) -> None:
        assert copywrite_entry(_entry(), [], client=_never_called()) == []


class TestParsing:
    def test_a_proposal_with_an_unknown_source_id_is_dropped(self) -> None:
        """The model must not attach a résumé line to something we never sent it."""
        entry = _entry("Hired six engineers")
        raw = json.dumps(
            {
                "bullets": [
                    {"source_id": "bullet:not-a-real-id", "text": "Invented a whole job"},
                    {
                        "source_id": f"bullet:{entry.bullets[0].bullet_id}",
                        "text": "Hired and mentored six engineers",
                    },
                ]
            }
        )

        proposals = parse_proposals(raw, entry, [])

        assert [p.text for p in proposals] == ["Hired and mentored six engineers"]

    def test_a_malformed_response_proposes_nothing_and_does_not_raise(self) -> None:
        """Copywriting is an improvement, never a dependency."""
        entry = _entry("Hired six engineers")
        assert parse_proposals("the model went rogue and wrote prose", entry, []) == []
        assert parse_proposals("", entry, []) == []

    def test_a_fenced_response_is_still_parsed(self) -> None:
        entry = _entry("Hired six engineers")
        body = {
            "bullets": [
                {"source_id": f"bullet:{entry.bullets[0].bullet_id}", "text": "Hired six"}
            ]
        }
        raw = f"Here you go:\n```json\n{json.dumps(body)}\n```"

        assert [p.text for p in parse_proposals(raw, entry, [])] == ["Hired six"]

    def test_a_proposal_carries_the_original_so_the_user_can_compare(self) -> None:
        entry = _entry("Ran CI")
        raw = json.dumps(
            {
                "bullets": [
                    {
                        "source_id": f"bullet:{entry.bullets[0].bullet_id}",
                        "text": "Rebuilt CI, cutting deploy failures",
                    }
                ]
            }
        )

        [proposal] = parse_proposals(raw, entry, [])

        assert proposal.original == "Ran CI"
        assert proposal.source_bullet_id == str(entry.bullets[0].bullet_id)


class TestAccept:
    def test_accepting_a_rewrite_SUPERSEDES_the_original_by_id(self) -> None:
        """So the résumé can never show both the polished line and the one it replaced."""
        original_id = "3f1b1d0e-0000-4000-8000-000000000001"
        proposal = Proposal(
            source_id=f"bullet:{original_id}",
            text="Rebuilt CI, cutting deploy failures 40%",
            original="Ran CI",
            source_bullet_id=original_id,
        )

        bullet = accept(proposal)

        assert bullet.text == "Rebuilt CI, cutting deploy failures 40%"
        assert bullet.source is BulletSource.GRILLED
        assert bullet.supersedes == UUID(original_id)

    def test_accepting_a_story_derived_rewrite_supersedes_nothing(self) -> None:
        """It ADDS a bullet the entry never had — there is no original to replace."""
        proposal = Proposal(
            source_id="story:abc",
            text="Cut deploy failures 40% by rebuilding CI",
            original="Cut deploy failures 40%",
            source_bullet_id=None,
        )

        bullet = accept(proposal)

        assert bullet.supersedes is None
        assert bullet.source is BulletSource.GRILLED


class _ScriptedClient:
    """A model client that returns a fixed response (no network)."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = 0

    def generate(self, *, model_id: str, system: str, user: str) -> str:
        self.calls += 1
        self.system = system
        self.user = user
        return self.response


def _never_called() -> Any:
    class _Boom:
        def generate(self, **_: Any) -> str:
            raise AssertionError("no material → the model must not be called")

    return _Boom()


class TestCopywriteEntry:
    def test_one_model_call_for_the_WHOLE_entry(self, monkeypatch: Any) -> None:
        """Batching is a hard requirement — a call per bullet makes the grill interminable."""
        from schema import Capability

        monkeypatch.setattr(
            "workflows.nodes._resolve_model", lambda _cap: "gemini-test"
        )
        entry = _entry("Ran CI", "Hired six engineers", "Owned the roadmap")
        client = _ScriptedClient(
            json.dumps(
                {
                    "bullets": [
                        {"source_id": f"bullet:{b.bullet_id}", "text": f"Rewritten: {b.text}"}
                        for b in entry.bullets
                    ]
                }
            )
        )

        proposals = copywrite_entry(entry, [], client=client)  # type: ignore[arg-type]

        assert client.calls == 1, "one call for the entry, not one per bullet"
        assert len(proposals) == 3
        assert Capability.REASONING_HIGH  # capability-routed, no hardcoded model id
