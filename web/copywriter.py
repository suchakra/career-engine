"""Résumé copywriting (CQ-4 / ARCHITECTURE §18, AD-18.1 + AD-18.2).

The missing stage. A résumé bullet used to be ``story.result`` **verbatim**
(:func:`web.resume_builder._bullet_for`) — text produced by the *grill*, whose job is metric
extraction and validation, not résumé prose. Nothing in the pipeline ever wrote a bullet, and
the one model call in the résumé path says so out loud ("your job is selection, a summary, and
skills"). So bullets read flat, and the S/T/A we collect during the grill were discarded at
render time, keeping only R — three quarters of the material, thrown away one line before the
PDF.

This is a **prompt + a pure node**, deliberately NOT an "agent" (AD-18.1): one deterministic
transform — (STAR story + the user's own bullets) → proposed résumé bullets — with no tools, no
memory and no autonomous loop.

**Human-validated and persisted** (AD-18.2): the proposals are shown to the user during the
grill, they accept / edit / reject each, and the accepted text is stored as a
``Bullet(source="grilled", supersedes=…)``. Two consequences that matter:
- no unreviewed prose can ever reach a PDF; and
- **export needs no model call at all** — the approved bullet is durable state, so assembly
  stays deterministic and costs the user nothing.

Everything here except :func:`copywrite_entry` is pure, so the prompt shape, the batching and
the response parsing are all tested without touching a model.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from integration.model_client import GeminiModelClient
from schema import Bullet, Capability, Entry, StarStory, UpgradeRequired
from workflows.prompts import COPYWRITER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

_MAX_BULLETS = 12
"""Bound one entry's proposals. A résumé role with more than a dozen lines is already
unreadable, and an unbounded prompt is an unbounded bill on the user's own key."""

_MAX_TEXT = 500
"""Must match ``AcceptedBullet.text``'s cap. A proposal the user cannot SAVE is worse than no
proposal at all: they would edit it, hit Keep, and get a 422 they cannot act on."""


@dataclass(frozen=True)
class Proposal:
    """One proposed rewrite, linked back to what it came from.

    ``source_bullet_id`` is set when the proposal rewrites one of the user's existing bullets
    (accepting it will ``supersede`` that bullet). It is ``None`` when the proposal comes from
    a STAR story that has no bullet of its own yet — accepting that one ADDS a bullet.
    """

    source_id: str
    text: str
    original: str
    source_bullet_id: str | None


def _source_items(entry: Entry, stories: list[StarStory]) -> list[dict[str, str]]:
    """The raw material for one entry, each item tagged with a stable ``source_id``.

    STAR stories come first (strongest evidence — a validated metric), then the user's own
    bullets. A bullet already covered by a story is NOT sent twice: the story carries the
    same achievement with more context, so rewriting both would propose two bullets for one
    thing. Matching is by containment, the same conservative rule the résumé assembler uses.

    **A story whose résumé line is already a bullet is offered as that BULLET, not as the
    story** (CQ-6). Once the user has approved prose for a story, that prose — not the grill's
    raw ``result`` — is the thing to polish further. Without this the second copywriter pass
    re-proposes an achievement the user already approved, and accepting it mints a *second*
    bullet claiming to speak for the same story: the loop never converges, and coverage counts
    the achievement twice. (The write side recorded the link from the start; this is the read
    side finally using it.)

    Superseded bullets are never offered — they are not on the résumé, and proposing a rewrite
    of a line the user has already replaced is noise at best.
    """
    superseded = {str(b.supersedes) for b in entry.bullets if b.supersedes is not None}
    live = [b for b in entry.bullets if str(b.bullet_id) not in superseded]
    spoken_for = {b.derived_from_story_id for b in live if b.derived_from_story_id}

    items: list[dict[str, str]] = []
    covered: set[str] = set()

    for story in stories:
        result = story.result.strip()
        if not result or str(story.story_id) in spoken_for:
            continue
        items.append(
            {
                "source_id": f"story:{story.story_id}",
                "situation": story.situation.strip(),
                "task": story.task.strip(),
                "action": story.action.strip(),
                "result": result,
            }
        )
        covered.add(" ".join(result.split()).casefold())

    for bullet in live:
        text = bullet.text.strip()
        if not text:
            continue
        norm = " ".join(text.split()).casefold()
        if any(norm in c or c in norm for c in covered):
            continue  # already said by a story, with more context
        items.append({"source_id": f"bullet:{bullet.bullet_id}", "existing_bullet": text})

    return items[:_MAX_BULLETS]


def build_prompt(entry: Entry, stories: list[StarStory]) -> str:
    """The user-side prompt for ONE entry — the whole entry in ONE model call.

    Batching per entry is a hard requirement (AD-18.2): a call per bullet would make the
    grill interminable, which is the obvious failure mode of this design.
    """
    return (
        f"EXPERIENCE: {entry.title}"
        + (f" at {entry.org}" if entry.org.strip() else "")
        + "\n\nMATERIAL:\n"
        + json.dumps(_source_items(entry, stories), indent=2)
    )


def parse_proposals(raw: str, entry: Entry, stories: list[StarStory]) -> list[Proposal]:
    """Parse the model's JSON into proposals, discarding anything unusable.

    Defensive by design — this text is going in front of the user and, if accepted, onto their
    résumé. A proposal is dropped unless its ``source_id`` is one we actually sent (the model
    must not invent a line attached to nothing) and its text is non-empty. A malformed response
    yields an empty list, and the caller falls back to the raw bullets: never a crash, never an
    empty résumé.
    """
    try:
        parsed = json.loads(_strip_fence(raw))
    except json.JSONDecodeError:
        logger.warning("copywriter: response was not valid JSON; proposing nothing")
        return []
    if not isinstance(parsed, dict):
        return []

    by_id = {item["source_id"]: item for item in _source_items(entry, stories)}
    bullet_text = {f"bullet:{b.bullet_id}": b.text for b in entry.bullets}
    story_text = {f"story:{s.story_id}": s.result for s in stories}

    proposals: list[Proposal] = []
    for item in parsed.get("bullets") or []:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("source_id", ""))
        # Collapse newlines and cap the length. The model can return prose, but a résumé
        # bullet is one line, and both the UI and AcceptedBullet cap at _MAX_TEXT — a proposal
        # the user cannot SAVE is worse than no proposal (they would edit it, hit Keep, and
        # get a 422 they cannot act on).
        text = " ".join(str(item.get("text", "")).split())[:_MAX_TEXT].strip()
        if not text or source_id not in by_id:
            logger.warning("copywriter: dropped a proposal with an unknown source_id")
            continue
        proposals.append(
            Proposal(
                source_id=source_id,
                text=text,
                original=bullet_text.get(source_id) or story_text.get(source_id, ""),
                source_bullet_id=(
                    source_id.split(":", 1)[1] if source_id.startswith("bullet:") else None
                ),
            )
        )
    return proposals


def _strip_fence(text: str) -> str:
    """Best-effort: pull the JSON object out of a fenced or chatty response."""
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start != -1 and end > start else text


def accept(proposal: Proposal) -> Bullet:
    """Turn an ACCEPTED proposal into the bullet that will be persisted.

    A rewrite of an existing bullet ``supersedes`` it — so the original stops appearing on the
    résumé, resolved **by id** rather than by guessing at text similarity.

    A proposal derived from a STAR story supersedes nothing (the entry had no such bullet);
    instead it records ``derived_from_story_id`` — *this bullet is that story's résumé line*
    (v2.12.0, CQ-6). Until CQ-6 that provenance was dropped on the floor, with two consequences:
    the assembler had no way to know the approved rewrite and the raw ``story.result`` were the
    same achievement, so the master résumé **listed it twice**; and the tailored résumé, which
    renders stories, shipped the **raw grill text** even though the user had approved better
    prose — making a liar of CQ-4's promise that no unreviewed text reaches a PDF.
    """
    from uuid import UUID

    from schema import BulletSource

    story_id = (
        proposal.source_id.split(":", 1)[1]
        if proposal.source_id.startswith("story:")
        else ""
    )
    return Bullet(
        text=proposal.text,
        source=BulletSource.GRILLED,
        supersedes=UUID(proposal.source_bullet_id) if proposal.source_bullet_id else None,
        derived_from_story_id=story_id,
    )


def copywrite_entry(
    entry: Entry, stories: list[StarStory], *, client: GeminiModelClient
) -> list[Proposal]:
    """One model call on the user's own key → proposed rewrites for one entry.

    Degrades to ``[]`` on any model or parse failure — the caller then keeps the user's raw
    bullets. A copywriting pass is an improvement, never a dependency: it must not be able to
    take the résumé down with it.
    """
    from workflows.nodes import _resolve_model

    items = _source_items(entry, stories)
    if not items:
        return []

    model_id = _resolve_model(Capability.REASONING_HIGH)
    if isinstance(model_id, UpgradeRequired):
        model_id = _resolve_model(Capability.SPEED_FAST)  # Free-mode fallback
    if not isinstance(model_id, str):
        return []

    raw = client.generate(
        model_id=model_id,
        system=COPYWRITER_SYSTEM_PROMPT,
        user=build_prompt(entry, stories),
    )
    return parse_proposals(raw, entry, stories)


__all__ = ["Proposal", "accept", "build_prompt", "copywrite_entry", "parse_proposals"]
