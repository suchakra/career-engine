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
from schema import (
    Bullet,
    Capability,
    CareerEngineState,
    Entry,
    ExperienceType,
    StarStory,
    UpgradeRequired,
)
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
class ResumeLine:
    """One rendered résumé line — WITH the identity of what it came from (CQ-6).

    A résumé line used to be a bare ``str``, and that single fact was the ceiling on three
    features at once:

    - the tailor preview could not say *which* portfolio object a line came from, so an edit
      there could never be persisted (CQ-6's whole point);
    - an approved copywriter rewrite could not be rendered *instead of* the raw ``story.result``
      it replaced, so the tailored résumé shipped raw grill text and listed the achievement twice;
    - de-duplication had to guess, by comparing prose.

    ``bullet_id`` is set when the line IS a stored :class:`schema.Bullet`. ``story_id`` is set
    when the line SPEAKS FOR a :class:`schema.StarStory`. Both are set for a bullet that was
    written to voice a story (``Bullet.derived_from_story_id``) — the common, healthy case.
    """

    text: str
    bullet_id: str = ""
    story_id: str = ""


def _line_id(line: ResumeLine) -> str:
    """Stable id for one résumé line — the token the tailor's model selects it by.

    A line backed by a stored bullet is addressed as that bullet (the durable object);
    otherwise it is addressed as the story it speaks for. Mirrors the copywriter's
    ``bullet:`` / ``story:`` convention so there is one id vocabulary, not two.
    """
    return f"bullet:{line.bullet_id}" if line.bullet_id else f"story:{line.story_id}"


@dataclass(frozen=True)
class RoleBlock:
    """One experience or education entry with its bullets, résumé-ready."""

    title: str
    org: str
    dates: str
    bullets: list[ResumeLine] = field(default_factory=list)
    entry_id: str = ""


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


def _covers(story_bullet: str, entry_bullet: str) -> bool:
    """LEGACY SHIM — text-containment dedup, used ONLY for link-less (pre-v2.11.0) stories.

    **Do not reach for this in new code, and do not delete it.**

    De-duplication is now decided by an ID link: a bullet is dropped when a story we already
    rendered declares — via ``StarStory.answers_bullet_id`` (v2.11.0) — that it answers *that*
    bullet. But **every story written before v2.11.0 has an empty link**, and that is all of the
    data in the live database. For those stories there is no link to reason with, and there
    never will be: which line they answered is not recoverable, and guessing it is precisely
    what this repo has banned everywhere else.

    So for a link-less story we keep doing exactly what we did before — containment, either
    direction, whitespace/case normalised — because the grilled result typically quotes or
    subsumes the original line it was extracted from. Deleting this outright (as an earlier
    draft of CQ-6 did) makes every grilled role of every returning user list its achievement
    TWICE on day one: the raw ``story.result`` *and* the original bullet it restated.

    It is still textual, so genuinely reworded overlap slips through — the same trade as
    before: a false match deletes the user's own words, a miss is a duplicate they can see.

    **Deletion condition:** when no ``metrics_validated`` story with an empty
    ``answers_bullet_id`` remains in live data, this function and its call site can go.
    """
    a = " ".join(story_bullet.split()).casefold()
    b = " ".join(entry_bullet.split()).casefold()
    if not a or not b:
        return False
    return a == b or b in a or a in b


def _said_by(bullet: Bullet, rendered: list[StarStory]) -> bool:
    """Is this bullet's achievement ALREADY on the résumé, said by a story we rendered?

    Three ways, in order of how much we trust them:

    1. ``bullet.derived_from_story_id`` names a rendered story — this bullet was written to
       voice that story, and the story's line has already been emitted (possibly by a
       *different* derived bullet; see the tiebreak in :func:`_entry_lines`). Two live bullets
       may point at one story, and without this check the loser of that tiebreak comes back as
       its own line — the duplicate bug, re-entering through the front door.
    2. ``story.answers_bullet_id`` names this bullet — the grill asked about THIS line and got
       a metric back (v2.11.0). The story's text *is* this line's résumé form.
    3. The story carries **no link at all** (pre-v2.11.0 — i.e. all live data): fall back to
       :func:`_covers`. This is the only text comparison left in the assembler, and it is
       scoped to data that predates the link.

    A story that HAS a link and names a *different* bullet says nothing about this one — we
    trust the link over the prose, which is the whole point of having it.
    """
    bullet_id = str(bullet.bullet_id)
    for story in rendered:
        if bullet.derived_from_story_id == str(story.story_id):
            return True
        if story.answers_bullet_id:
            if story.answers_bullet_id == bullet_id:
                return True
            continue
        if _covers(_bullet_for(story), bullet.text):
            return True
    return False


def _entry_lines(entry: Entry, stories: list[StarStory]) -> list[ResumeLine]:
    """Every line the MASTER résumé would render for one entry, in order.

    This is the single definition of "the candidate's material for this role". The tailored
    résumé is a *selection* from these same lines (never a separately-assembled set), which is
    what keeps the tailor's catalog and the rendered document from ever drifting apart.

    1. **One line per validated story** — its *derived bullet* if the user has approved or
       written one (``Bullet.derived_from_story_id``), else the raw ``story.result``. This is
       what puts human-approved prose on the résumé instead of raw grill text.
    2. **Then the entry's own bullets** — what the user wrote or uploaded — minus anything a
       rendered story already said (:func:`_said_by`). Without step 2, uploading a good résumé
       and asking for one back returns an EMPTY document: every line the user supplied is
       discarded because no story has been extracted from it yet.

    Education is deliberately step-1 only: carrying its raw bullets would spill parsed
    coursework, honours and thesis blurbs into the education section, which the renderer has
    never had to lay out.
    """
    superseded = {str(b.supersedes) for b in entry.bullets if b.supersedes is not None}
    live = [b for b in entry.bullets if str(b.bullet_id) not in superseded]

    # Which bullet speaks for which story. Two live bullets CAN name the same story (e.g. the
    # user overwrites a line in the tailor preview that a copywriter rewrite already covers);
    # `Bullet` has no timestamp, so the only deterministic tiebreak available is document
    # order — the last one wins, i.e. the most recently appended.
    derived: dict[str, Bullet] = {
        b.derived_from_story_id: b for b in live if b.derived_from_story_id
    }

    lines: list[ResumeLine] = []
    rendered: list[StarStory] = []
    for story in stories:
        story_id = str(story.story_id)
        bullet = derived.get(story_id)
        # A blank derived bullet must fall back to the story, not delete it. Losing the polish
        # is a cosmetic regression; losing the ACHIEVEMENT is data disappearing off a résumé.
        # Unreachable today (accepted text is min_length=1 and blank edits are refused), which
        # is precisely why it is worth a fallback rather than a trusted invariant.
        text = (bullet.text.strip() if bullet is not None else "") or _bullet_for(story)
        if not text:
            continue
        if bullet is not None and not bullet.text.strip():
            bullet = None  # the line is the story's, so it must not claim the bullet's id
        lines.append(
            ResumeLine(
                text=text,
                bullet_id=str(bullet.bullet_id) if bullet is not None else "",
                story_id=story_id,
            )
        )
        rendered.append(story)

    if entry.type is ExperienceType.EDUCATION:
        return lines

    emitted = {line.bullet_id for line in lines if line.bullet_id}
    lines.extend(
        ResumeLine(text=b.text.strip(), bullet_id=str(b.bullet_id))
        for b in live
        if b.text.strip() and str(b.bullet_id) not in emitted and not _said_by(b, rendered)
    )
    return lines


def resume_lines(state: CareerEngineState) -> dict[str, list[ResumeLine]]:
    """The master résumé's lines, keyed by ``entry_id`` — the tailor's catalog, too.

    Defining the catalog as *"the lines the master would render"* (rather than as its own
    hand-rolled query) is what guarantees the model can only ever select something that will
    actually render, and that anything renderable can be selected.
    """
    by_entry: dict[str, list[StarStory]] = {}
    for story in state.extracted_star_stories:
        if story.metrics_validated:
            by_entry.setdefault(story.entry_id, []).append(story)
    return {
        str(entry.entry_id): _entry_lines(entry, by_entry.get(str(entry.entry_id), []))
        for entry in state.work_timeline
    }


def assemble_resume(
    state: CareerEngineState,
    *,
    contact: Contact,
    summary: str,
    skills: list[str],
    selected_line_ids: set[str] | None = None,
) -> StructuredResume:
    """Deterministically build a StructuredResume from the session (grouped by role).

    ``selected_line_ids`` (``bullet:<id>`` / ``story:<id>``, see :func:`_line_id`) keeps only
    those lines — the JD-tailored résumé. ``None`` keeps everything — the master résumé.
    Education entries are listed regardless. Experience order follows ``work_timeline``.
    """
    lines_by_entry = resume_lines(state)

    experience: list[RoleBlock] = []
    education: list[RoleBlock] = []
    for entry in state.work_timeline:
        lines = lines_by_entry[str(entry.entry_id)]
        if selected_line_ids is not None:
            lines = [line for line in lines if _line_id(line) in selected_line_ids]
        block = RoleBlock(
            title=entry.title,
            org=entry.org,
            dates=_dates(entry),
            bullets=lines,
            entry_id=str(entry.entry_id),
        )
        if entry.type is ExperienceType.EDUCATION:
            education.append(block)
        elif lines:  # a work role earns a spot only if it has something to show
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

    The master résumé is the user's COMPLETE record, so it carries the lines they wrote /
    uploaded as well as the achievements we have grilled a metric out of. Without that,
    uploading a good résumé and asking for a master résumé returned an empty document.
    """
    return assemble_resume(
        state,
        contact=contact or Contact(),
        summary=state.professional_summary,
        skills=[],
        selected_line_ids=None,
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

    One model call selects the most JD-relevant lines, writes a tailored summary, and lists
    JD-aligned skills; the résumé structure (experience by role) is then assembled
    deterministically from ``entry_id`` links.

    **The catalog is exactly the set of lines the MASTER résumé would render** (CQ-6). It used
    to be validated STAR stories only, which meant a user who uploaded a strong résumé and
    tailored it before grilling got an EMPTY document — the same bug we had already fixed for
    the master résumé, still live here. It also meant a copywriter-approved rewrite never
    reached a tailored résumé: it shipped the raw grill text instead.
    """
    from workflows.nodes import _resolve_model, set_model_client_factory

    set_model_client_factory(lambda: client)

    lines_by_entry = resume_lines(state)
    entry_by_id = {str(e.entry_id): e for e in state.work_timeline}
    catalog = [
        {
            "id": _line_id(line),
            "role": f"{entry_by_id[entry_id].title} at {entry_by_id[entry_id].org}",
            "achievement": line.text,
        }
        for entry_id, lines in lines_by_entry.items()
        for line in lines
        if entry_id in entry_by_id
    ]

    if not catalog:  # nothing to say yet → an honest empty résumé (never crash)
        return assemble_resume(state, contact=contact, summary="", skills=[], selected_line_ids=set())

    model_id = _resolve_model(Capability.REASONING_HIGH)
    if isinstance(model_id, UpgradeRequired):
        model_id = _resolve_model(Capability.SPEED_FAST)  # Free-mode fallback
    model_id_str = model_id if isinstance(model_id, str) else ""

    user_prompt = (
        f"JOB DESCRIPTION:\n{jd_text}\n\n"
        f"CANDIDATE ACHIEVEMENTS (catalog):\n{json.dumps(catalog, indent=2)}"
    )
    stripped_instructions = _instructions.strip()
    extra = (
        f"\n\n[Additional instructions — apply to this résumé only]:\n{stripped_instructions}"
        if stripped_instructions else ""
    )
    effective_user = user_prompt + extra
    raw = client.generate(model_id=model_id_str, system=STRUCTURED_TAILOR_SYSTEM_PROMPT, user=effective_user)
    parsed = _extract_json_object(raw)

    summary = str(parsed.get("tailored_summary", "")).strip()
    skills = [str(s).strip() for s in (parsed.get("skills") or []) if str(s).strip()]
    catalog_ids = {c["id"] for c in catalog}
    # Keep only ids the model returned that actually exist. A parse miss OR a set of
    # all-invalid ids must NOT drop the résumé — fall back to everything the master would
    # render. (Pre-CQ-6 this fell back to validated stories only; the safety path is now
    # wider because the catalog is wider.)
    selected = {str(i) for i in (parsed.get("selected_achievement_ids") or []) if str(i) in catalog_ids}
    if not selected:
        selected = set(catalog_ids)

    # 4E: always include the lines of experiences the user PINNED as tailoring priority, even
    # if the model didn't pick them — they said explicitly that this role matters. Resolved
    # per ENTRY, so it covers both kinds of line id; the old code looked ids up in a
    # story→entry map, which returned "" for a bullet-backed line and would have silently
    # dropped a pinned role whose material is bullets the user uploaded but hasn't grilled.
    pinned = {
        _line_id(line)
        for entry in state.work_timeline
        if entry.highlighted
        for line in lines_by_entry.get(str(entry.entry_id), [])
    }

    return assemble_resume(
        state,
        contact=contact,
        summary=summary,
        skills=skills,
        selected_line_ids=selected | pinned,
    )


__all__ = [
    "Contact",
    "ResumeLine",
    "RoleBlock",
    "StructuredResume",
    "assemble_resume",
    "master_structured_resume",
    "resume_lines",
    "tailor_structured_resume",
]
