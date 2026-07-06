"""Assemble a REAL, ATS-safe résumé from a session's portfolio + a job description.

The earlier tailor produced a summary + a flat list of "talking points" (with an
internal "why it fits" note) — not a résumé. This builds a proper structure:
contact header · JD-aligned skills · **experience grouped by role**
(company · title · dates, quantified bullets under each) · education.

The key move: bullets live under their employer/role. Every ``StarStory`` already
carries an ``entry_id`` linking it to its ``Entry`` (org/title/dates), so grouping
is deterministic — no model call needed for structure. The model is used only for
JD-aware *selection*, the tailored *summary*, and JD-aligned *skills*.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from integration.model_client import GeminiModelClient
from schema import Capability, CareerEngineState, Entry, ExperienceType, StarStory, UpgradeRequired
from workflows.prompts import STRUCTURED_TAILOR_SYSTEM_PROMPT


@dataclass(frozen=True)
class Contact:
    """Résumé header identity (provided by the user; not model-generated)."""

    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    links: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RoleBlock:
    """One experience or education entry with its bullets, résumé-ready."""

    title: str
    org: str
    dates: str
    bullets: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class StructuredResume:
    """A real résumé: contact · summary · skills · experience (by role) · education."""

    contact: Contact
    summary: str
    skills: list[str]
    experience: list[RoleBlock]
    education: list[RoleBlock]

    @property
    def is_empty(self) -> bool:
        """True when there's nothing to show (no summary, experience, OR education).

        Education counts — an early-career résumé may be education-only.
        """
        return not (self.summary.strip() or self.experience or self.education)

    def to_json(self) -> str:
        """Serialise to JSON (persisted as an Application's ``tailored_resume_json``).

        ``StructuredResume`` is a dataclass (not a Pydantic model), so it has no
        ``model_dump_json``; this is the canonical serialization seam.
        """
        return json.dumps(asdict(self))


def _dates(entry: Entry) -> str:
    """Human date range: 'YYYY - present', 'YYYY - YYYY', or '' if both unknown."""
    if not entry.start_date and not entry.end_date:
        return ""
    return f"{entry.start_date or '?'} - {entry.end_date or 'present'}"


def _bullet_for(story: StarStory) -> str:
    """A metric-first résumé bullet from a STAR story — the quantified result.

    The result IS the quantified outcome (the metric), so it leads the bullet;
    the action is only a fallback when there is no result text.
    """
    return story.result.strip() or story.action.strip()


def _extract_json_object(text: str) -> dict[str, Any]:
    """Best-effort JSON object from a model response (handles fences / prose)."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        parsed: object = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def assemble_resume(
    state: CareerEngineState,
    *,
    contact: Contact,
    summary: str,
    skills: list[str],
    selected_story_ids: list[str] | None = None,
) -> StructuredResume:
    """Deterministically build a StructuredResume from the session (grouped by role).

    Only ``metrics_validated`` stories are used. If ``selected_story_ids`` is given,
    experience bullets are limited to that selection (JD-tailored); otherwise all
    validated stories are included (master résumé). Education entries are listed
    regardless of stories. Experience order follows ``work_timeline`` (newest-first).
    """
    selected = set(selected_story_ids) if selected_story_ids is not None else None
    by_entry: dict[str, list[StarStory]] = {}
    for story in state.extracted_star_stories:
        if not story.metrics_validated:
            continue
        if selected is not None and str(story.story_id) not in selected:
            continue
        by_entry.setdefault(story.entry_id, []).append(story)

    experience: list[RoleBlock] = []
    education: list[RoleBlock] = []
    for entry in state.work_timeline:
        stories = by_entry.get(str(entry.entry_id), [])
        bullets = [b for b in (_bullet_for(s) for s in stories) if b]
        block = RoleBlock(title=entry.title, org=entry.org, dates=_dates(entry), bullets=bullets)
        if entry.type is ExperienceType.EDUCATION:
            education.append(block)
        elif bullets:  # a work role earns a spot only if it has quantified bullets
            experience.append(block)

    return StructuredResume(
        contact=contact,
        summary=summary.strip(),
        skills=[s for s in skills if s.strip()],
        experience=experience,
        education=education,
    )


def master_structured_resume(
    state: CareerEngineState, *, contact: Contact | None = None
) -> StructuredResume:
    """Assemble the user's MASTER résumé — every quantified achievement, no JD tailoring.

    The same :class:`StructuredResume` schema and renderer as the tailored résumé (5C):
    all validated stories (no ``selected_story_ids``), grouped by role, with the
    profile summary. Skills are left to the tailored pass (they are JD-aligned there).
    """
    return assemble_resume(
        state,
        contact=contact or Contact(),
        summary=state.professional_summary,
        skills=[],
        selected_story_ids=None,
    )


def tailor_structured_resume(
    state: CareerEngineState,
    jd_text: str,
    contact: Contact,
    *,
    client: GeminiModelClient,
    _instructions: str = "",
) -> StructuredResume:
    """Tailor to a JD and return a real, structured résumé.

    One model call selects the most JD-relevant achievements, writes a tailored
    summary, and lists JD-aligned skills; the résumé structure (experience by role)
    is then assembled deterministically from ``entry_id`` links.
    """
    from workflows.nodes import _resolve_model, set_model_client_factory

    set_model_client_factory(lambda: client)

    entry_by_id = {str(e.entry_id): e for e in state.work_timeline}
    catalog = [
        {
            "id": str(s.story_id),
            "role": f"{entry_by_id[s.entry_id].title} at {entry_by_id[s.entry_id].org}"
            if s.entry_id in entry_by_id
            else "",
            "achievement": s.result.strip(),
        }
        for s in state.extracted_star_stories
        if s.metrics_validated and s.result.strip()
    ]

    if not catalog:  # nothing grilled yet → an honest empty résumé (never crash)
        return assemble_resume(state, contact=contact, summary="", skills=[], selected_story_ids=[])

    model_id = _resolve_model(Capability.REASONING_HIGH)
    if isinstance(model_id, UpgradeRequired):
        model_id = _resolve_model(Capability.SPEED_FAST)  # Free-mode fallback
    model_id_str = model_id if isinstance(model_id, str) else ""

    user_prompt = (
        f"JOB DESCRIPTION:\n{jd_text}\n\n"
        f"CANDIDATE ACHIEVEMENTS (catalog):\n{json.dumps(catalog, indent=2)}"
    )
    extra = (
        f"\n\n[Additional instructions — apply to this r\u00e9sum\u00e9 only]:\n"
        f"{_instructions.strip()}"
        if _instructions.strip() else ""
    )
    effective_user = user_prompt + extra
    raw = client.generate(model_id=model_id_str, system=STRUCTURED_TAILOR_SYSTEM_PROMPT, user=effective_user)
    parsed = _extract_json_object(raw)

    summary = str(parsed.get("tailored_summary", "")).strip()
    skills = [str(s).strip() for s in (parsed.get("skills") or []) if str(s).strip()]
    catalog_ids = {c["id"] for c in catalog}
    # Keep only ids the model returned that actually exist. A parse miss OR a set of
    # all-invalid ids must NOT drop the résumé — fall back to all validated stories.
    selected = [str(i) for i in (parsed.get("selected_achievement_ids") or []) if str(i) in catalog_ids]
    if not selected:
        selected = [c["id"] for c in catalog]

    # 4E: always include achievements from experiences the user PINNED as tailoring
    # priority — even if the model didn't pick them — since the user explicitly
    # prioritized them. Pinned first, then the model's picks, deduped.
    highlighted_entry_ids = {str(e.entry_id) for e in state.work_timeline if e.highlighted}
    if highlighted_entry_ids:
        # StarStory.entry_id is already a str per schema; no coercion needed.
        story_entry = {str(s.story_id): s.entry_id for s in state.extracted_star_stories}
        pinned = [c["id"] for c in catalog if story_entry.get(c["id"], "") in highlighted_entry_ids]
        selected = list(dict.fromkeys([*pinned, *selected]))

    return assemble_resume(
        state, contact=contact, summary=summary, skills=skills, selected_story_ids=selected
    )


__all__ = [
    "Contact",
    "RoleBlock",
    "StructuredResume",
    "assemble_resume",
    "master_structured_resume",
    "tailor_structured_resume",
]
