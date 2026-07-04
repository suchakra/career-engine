"""Web Tailor flow: turn a session's portfolio + a JD into a tailored résumé.

Reuses the workflow nodes (``finalize_master_resume_node`` → ``tailor_node``) that
the CLI tailor uses, but drives them directly so the web can tailor from the user's
CURRENT progress without marking the discovery session COMPLETE (tailoring is never
blocked — a thinner portfolio just yields a thinner result).

Two layers, matching the rest of ``web/``:
- :func:`build_tailored_resume_json` — runs the nodes on the user's installed model
  client and returns the tailored résumé JSON string.
- :func:`parse_tailored` / :func:`tailored_to_markdown` — PURE helpers (no model, no
  Streamlit) that turn that JSON into a display-ready object and a Markdown export.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from integration.model_client import GeminiModelClient
from schema import CareerEngineState


@dataclass(frozen=True)
class TailoredAchievement:
    """One selected, JD-relevant achievement (display-ready)."""

    pillar: str
    headline: str
    full_text: str
    relevance_note: str


@dataclass(frozen=True)
class TailoredResume:
    """A parsed tailored résumé: a summary + the achievements chosen for the JD."""

    summary: str
    achievements: list[TailoredAchievement] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """True when there's nothing tailored to show (no summary, no achievements)."""
        return not (self.summary.strip() or self.achievements)


def build_tailored_resume_json(
    state: CareerEngineState, jd_text: str, *, client: GeminiModelClient
) -> str:
    """Tailor the session's portfolio to ``jd_text``; return the tailored résumé JSON.

    Ensures a master résumé exists first (assembling one from the current validated
    stories if the grill hasn't been finalized), then runs the tailor node. Does NOT
    persist a phase change — the caller decides what to store — so tailoring never
    ends an in-progress grill.
    """
    from workflows.nodes import (
        finalize_master_resume_node,
        set_model_client_factory,
        tailor_node,
    )

    set_model_client_factory(lambda: client)
    work = state
    if not work.master_resume_json.strip():
        work = finalize_master_resume_node(work)  # assemble a master from current stories
    work = work.model_copy(update={"jd_text": jd_text})
    work = tailor_node(work)
    return work.tailored_resume_json


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


def parse_tailored(tailored_json: str) -> TailoredResume:
    """Parse the tailor node's JSON into a display-ready :class:`TailoredResume`.

    Robust to messy model output — an unparseable payload yields an empty résumé
    rather than raising, so the UI degrades gracefully.
    """
    data = _extract_json_object(tailored_json or "")
    summary = str(data.get("tailored_summary", "")).strip()
    achievements: list[TailoredAchievement] = []
    for item in data.get("selected_achievements", []) or []:
        if not isinstance(item, dict):
            continue
        headline = str(item.get("headline", "")).strip()
        if not headline:
            continue
        achievements.append(
            TailoredAchievement(
                pillar=str(item.get("pillar", "")).strip(),
                headline=headline,
                full_text=str(item.get("full_text", "")).strip(),
                relevance_note=str(item.get("relevance_note", "")).strip(),
            )
        )
    return TailoredResume(summary=summary, achievements=achievements)


def tailored_to_markdown(tailored: TailoredResume, *, heading: str = "Tailored résumé") -> str:
    """Render a tailored résumé as Markdown (ATS-friendly plain text export)."""
    lines: list[str] = [f"# {heading}", ""]
    if tailored.summary:
        lines += [tailored.summary, ""]
    if tailored.achievements:
        lines += ["## Selected achievements", ""]
        for a in tailored.achievements:
            lines.append(f"- **{a.headline}**")
            if a.full_text:
                lines.append(f"  {a.full_text}")
            if a.relevance_note:
                lines.append(f"  _Why it fits: {a.relevance_note}_")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "TailoredAchievement",
    "TailoredResume",
    "build_tailored_resume_json",
    "parse_tailored",
    "tailored_to_markdown",
]
