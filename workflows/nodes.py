"""Atomic workflow node implementations — Phase 1.5 (entry-based grill loop).

Every node is a PURE function: (CareerEngineState) -> CareerEngineState.
No UI imports.  No direct Firestore calls.  No hardcoded model names.
No datetime.now calls — use state.reference_date for determinism.
Model access goes through models.registry.get_registry().get_model_id().

On capability shortfall, nodes return UpgradeRequired (typed); they never raise.

Dependency injection:
    Model client access is abstracted through _get_model_client(), which can be
    replaced in tests via set_model_client_factory().  This keeps the nodes
    unit-testable without a live API key.

StarStory immutability:
    StarStory is frozen=True (config).  Nodes create NEW instances rather than
    mutating existing ones, using model_copy() or direct construction.

Entry-based grilling (v2.0.0):
    The grill loop now targets the Entry at state.grill_frontier (a UUID string).
    On a validated answer, a StarStory(entry_id=frontier) is attached, the entry
    status is set to 'grilled', and grill_frontier advances backward-chronologically
    to the next entry needing work.  The frontier is jumpable: setting grill_frontier
    explicitly makes that entry the next grill target.

ADK 2.0 wiring note:
    discovery_graph.py wraps each pure function in a FunctionNode with a thin
    ctx-based shim that reads CareerEngineState from ctx.state, calls the pure
    function, and writes the result back.  The pure functions here have no ADK
    dependency — they are testable stand-alone.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from config import AccessMode, get_settings
from models.registry import get_registry
from schema import (
    Bullet,
    Capability,
    CareerEngineState,
    Entry,
    EntryStatus,
    ExperienceType,
    PhaseStatus,
    StarStory,
    UpgradeRequired,
)
from web.coverage import entry_coverage, entry_needs_work
from workflows.prompts import (
    CHECKPOINT_SUMMARY_PROMPT,
    DISCOVERY_SYSTEM_PROMPT,
    FINALIZE_SYSTEM_PROMPT,
    GRILL_SYSTEM_PROMPT,
    INGEST_SYSTEM_PROMPT,
    METRIC_EXTRACTION_PROMPT,
    TAILOR_SYSTEM_PROMPT,
)

# ── Model client injection ────────────────────────────────────────────────────
# The factory returns any object with a .generate(model_id, system, user) -> str
# interface.  Tests replace this with a mock; production uses the real genai client.

ModelClient = Any  # Protocol: .generate(model_id: str, system: str, user: str) -> str

# Free-Mode Pro-escalation gate: after this many failed Flash+CoT metric-extraction
# attempts on a SINGLE entry, the grill node emits UpgradeRequired recommending a
# Pro reasoning model. Set above the 5-turn checkpoint boundary so the checkpoint
# brake (pause + summarize) always fires first; escalation is the considered next
# step for a user who stays vague on the same entry past a checkpoint.
_MAX_FLASH_GRILL_ATTEMPTS: int = 6


def _default_client_factory() -> ModelClient:
    """Return the default genai-backed model client."""
    import google.genai as genai
    from google.genai import types as gtypes

    settings = get_settings()
    api_key = settings.gemini_api_key or settings.dev_gemini_key or None
    # A per-request timeout (ms) so a network stall raises instead of hanging the
    # graph. See workflows/observability.py for the visibility half.
    http_options = gtypes.HttpOptions(timeout=int(settings.model_timeout_seconds * 1000))

    class _GenaiClient:
        """Thin wrapper around google.genai for generate() calls."""

        def __init__(self, key: str | None) -> None:
            """Initialise with optional API key + a request timeout."""
            self._client = (
                genai.Client(api_key=key, http_options=http_options)
                if key
                else genai.Client(http_options=http_options)
            )

        def generate(self, model_id: str, system: str, user: str) -> str:
            """Call generate_content (retrying transient 5xx) and return the text."""
            from integration.model_client import _call_with_retry

            response = _call_with_retry(
                lambda: self._client.models.generate_content(
                    model=model_id,
                    contents=user,
                    config=gtypes.GenerateContentConfig(system_instruction=system),
                )
            )
            return response.text or ""

    return _GenaiClient(api_key)


_client_factory: Callable[[], ModelClient] = _default_client_factory


class _MonitoredModelClient:
    """Wraps any ModelClient to log + time every ``generate`` call.

    Delegates to the wrapped client unchanged (so injected test mocks behave
    identically); it only adds a :func:`~workflows.observability.log_operation`
    bracket around the call, surfacing slow/failed model calls in the logs.
    """

    def __init__(self, delegate: ModelClient) -> None:
        """Wrap a delegate model client."""
        self._delegate = delegate

    def generate(self, model_id: str, system: str, user: str) -> str:
        """Time + log the delegate's generate call."""
        from workflows.observability import get_logger, log_operation

        with log_operation(
            "model.generate", logger=get_logger("nodes"), model_id=model_id
        ):
            result: str = self._delegate.generate(model_id, system, user)
        return result


def set_model_client_factory(factory: Callable[[], ModelClient]) -> None:
    """Replace the model client factory (for testing).

    Call this before the node functions are invoked to inject a mock client
    that does not make live API calls.
    """
    global _client_factory
    _client_factory = factory


def _get_model_client() -> ModelClient:
    """Return the current model client (real or injected mock), monitored."""
    return _MonitoredModelClient(_client_factory())


# ── Internal helpers ──────────────────────────────────────────────────────────


def _resolve_model(capability: Capability) -> str | UpgradeRequired:
    """Resolve a capability to a model ID via the registry."""
    registry = get_registry()
    settings = get_settings()
    return registry.get_model_id(capability, access_mode=settings.access_mode)


def _parse_json_response(text: str) -> dict[str, Any]:
    """Extract and parse a JSON object from a model response string.

    Handles markdown fences (```json ... ```) and bare JSON objects.
    Returns an empty dict on parse failure.
    """
    # Strip markdown fences if present
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    # Find first JSON object
    obj_match = re.search(r"\{.*\}", text, re.DOTALL)
    if not obj_match:
        return {}
    try:
        parsed: object = json.loads(obj_match.group(0))
    except json.JSONDecodeError:
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


def _contains_real_metric(result_text: str) -> bool:
    """Return True if result_text contains at least one concrete numeric metric.

    A real metric is any of:
    - A numeric value with a unit (digits followed by ms, %, $, k, M, etc.)
    - A before/after comparison containing numbers
    - A count or scale figure (e.g. "across 40 services", "2M requests")
    - Early-career / non-eng: users/downloads/stars, team size, competition rank,
      dataset scale, citations, GPA
    """
    if not result_text:
        return False
    # Look for numeric patterns indicating a metric
    patterns = [
        # Engineering / performance metrics
        r"\d+\s*ms\b",  # latency (milliseconds)
        r"\d+\s*s\b",  # seconds
        r"\d+\s*%",  # percentages
        r"\$\s*\d+",  # dollar amounts
        r"\d+\s*[kKmMbB]\b",  # k/M/B scale suffixes
        r"\d+\s+(?:services?|servers?|nodes?|instances?|engineers?|customers?|requests?)",
        r"\bfrom\s+\d",  # before/after pattern ("from 800ms...")
        r"\d+\s*(?:minutes?|hours?|days?)",  # time durations
        r"\d+x\b",  # multiplier (2x, 10x)
        r"\d+\.\d+",  # decimal numbers
        # Early-career / non-eng patterns
        r"\d+\s+(?:users?|downloads?|installs?)",  # users/downloads/installs
        r"\d+\s+(?:stars?)",  # GitHub stars
        r"\d+\s+(?:forks?)",  # forks
        r"team\s+(?:of\s+)?\d+",  # team size ("team of 5")
        r"\d+[-\s]+(?:person|member|people)\s+team",  # team size alt form (6-person or 6 person)
        r"\d+\s+(?:participants?|students?|attendees?|members?)",  # group size
        r"(?:rank(?:ed)?|place[d]?|finish(?:ed)?)\s+(?:in\s+)?(?:top\s+)?\d+",  # competition rank
        r"(?:1st|2nd|3rd|\d+th)\s+(?:place|prize|rank)",  # ordinal rank
        r"\d+[kK]\s*(?:rows?|samples?|records?|examples?|entries|tokens?)",  # dataset scale
        r"\d+\s+(?:citations?|references?|papers?)",  # academic citations
        r"cited\s+\d+\s+times?",  # citation count
        r"\b(?:gpa|grade)\s*(?:of\s+)?\d+\.\d+",  # GPA
        r"\d+\.\d+\s*(?:gpa|\/4\.0|\/5\.0)",  # GPA format alt
    ]
    for pattern in patterns:
        if re.search(pattern, result_text, re.IGNORECASE):
            return True
    return False


# ── Entry timeline helpers ────────────────────────────────────────────────────


def _parse_year_from_date(date_str: str) -> int | None:
    """Extract the year from a YYYY-MM or YYYY date string; return None on failure."""
    if not date_str:
        return None
    try:
        return int(date_str.split("-")[0])
    except (ValueError, IndexError):
        return None


def _is_soft_horizon(entry: Entry, reference_date: str) -> bool:
    """Return True if an entry's end_date is older than ~15 years before reference_date.

    Uses reference_date — NEVER calls datetime.now directly.
    An entry with empty end_date (present) is never in the soft horizon.
    """
    if not entry.end_date:
        return False  # present → never soft-horizon
    if not reference_date:
        return False  # no clock → cannot judge

    ref_year = _parse_year_from_date(reference_date)
    end_year = _parse_year_from_date(entry.end_date)
    if ref_year is None or end_year is None:
        return False
    return (ref_year - end_year) >= 15


def _has_metric_bullet(entry: Entry) -> bool:
    """Return True if the entry already has at least one metric-bearing bullet."""
    return any(_contains_real_metric(b) for b in entry.bullet_texts)


def _grilled_before_the_link_existed(entry: Entry, stories: list[StarStory]) -> bool:
    """Was this entry grilled BEFORE the story→bullet link existed (pre-v2.11.0)?

    Every story written before CQ-5b has an empty ``answers_bullet_id``, because per-bullet
    targeting did not exist. Coverage therefore reads such an entry as 0-of-N covered — and
    once coverage steers the grill, that would silently RE-OPEN the finished portfolio of every
    returning user and march them back through work they already did. (Found by adversarial
    review against a real legacy-shaped state; it is not hypothetical — every story in the live
    qa data looks like this.)

    We cannot know which line those stories answered, so we do not pretend to: such an entry is
    left alone by the AUTOMATIC gates. The user can still aim the grill at it explicitly with
    "Grill me about this" — see ``entry_still_needs_grilling(..., explicit=True)``.
    """
    return entry.status is EntryStatus.GRILLED and any(
        s.metrics_validated and not s.answers_bullet_id for s in stories
    )


def entry_still_needs_grilling(
    entry: Entry, stories: list[StarStory], *, explicit: bool = False
) -> bool:
    """THE single definition of "this entry is not done" (CQ-5b).

    Every gate in the grill must ask this same question, or they diverge and the grill either
    abandons work (the router says finalize while the frontier holds an entry) or spins (the
    frontier holds an entry the question-targeter has nothing to ask about). Both happened.

    ``stories`` must be THIS ENTRY'S stories. ``explicit=True`` means the USER pointed the grill
    at this entry, which overrides the pre-v2.11.0 grandfather above — if they ask to be grilled
    on it, they get grilled on it.
    """
    if entry.status is EntryStatus.SKIPPED:
        return False
    if entry.status in (EntryStatus.NEEDS_QUANTIFYING, EntryStatus.DOCUMENTED):
        return True
    if not explicit and _grilled_before_the_link_existed(entry, stories):
        return False
    # GRILLED / SUMMARIZED, but still carrying lines nobody has dealt with.
    return entry_needs_work(entry, stories)


def stories_for(entry: Entry, stories: list[StarStory]) -> list[StarStory]:
    """This entry's stories. Filtering INCONSISTENTLY is how the two coverage views diverged."""
    return [s for s in stories if s.entry_id == str(entry.entry_id)]


def _next_uncovered_bullet(entry: Entry, stories: list[StarStory]) -> Bullet | None:
    """The bullet the grill should ask about next on this entry (CQ-5b).

    The FIRST uncovered one, in the order the user wrote them — a résumé is ordered by the
    author's own sense of importance, so working top-down matches their intent and is
    predictable. Returns None when nothing is outstanding.
    """
    outstanding = set(entry_coverage(entry, stories).uncovered_bullet_ids)
    return next((b for b in entry.bullets if str(b.bullet_id) in outstanding), None)


def _find_entry_by_id(timeline: list[Entry], entry_id: str) -> Entry | None:
    """Find an entry in the timeline by its entry_id string; return None if not found."""
    for entry in timeline:
        if str(entry.entry_id) == entry_id:
            return entry
    return None


# Relative substance of an experience type — used to break recency ties so a
# recent SUBSTANTIVE role (a job) is grilled before a recent trivial one (a
# one-day volunteer gig / a course). Higher = grill sooner.
_TYPE_WEIGHT: dict[ExperienceType, int] = {
    ExperienceType.FULL_TIME: 5,
    ExperienceType.LEADERSHIP: 5,
    ExperienceType.RESEARCH: 4,
    ExperienceType.OPEN_SOURCE: 4,
    ExperienceType.PART_TIME: 3,
    ExperienceType.PROJECT: 3,
    ExperienceType.INTERNSHIP: 2,
    ExperienceType.EDUCATION: 1,
    ExperienceType.OTHER: 1,
}
# A current role (empty end_date = "present") is newer than any dated one.
_PRESENT_SENTINEL_YEAR = 10_000


def _frontier_sort_key(entry: Entry) -> tuple[int, int, int]:
    """Ranking key for grilling: (recency, substance, start-year), newest/most first.

    Recency is driven by ``end_date`` — a CURRENT role (empty end_date) ranks above
    any dated one, which is what a reviewer expects (grill the roles you're in / just
    left first). Substance (experience type) breaks recency ties so a recent job
    outranks a recent trivial entry.

    An empty end_date means "present" ONLY for ongoing work — NOT for EDUCATION. A
    résumé parser frequently emits an empty end_date for a *completed* degree; if we
    treated that as "present" the ancient degree would float above the user's real
    current job (the "grilling starts from ancient history" bug). For EDUCATION with
    no end_date we rank by start year instead, so it sits with its actual era.
    """
    start_year = _parse_year_from_date(entry.start_date) or -1
    if not entry.end_date:
        # EDUCATION with no end date → rank by its start era, not "present".
        end_year = start_year if entry.type is ExperienceType.EDUCATION else _PRESENT_SENTINEL_YEAR
    else:
        end_year = _parse_year_from_date(entry.end_date) or -1
    return (end_year, _TYPE_WEIGHT.get(entry.type, 1), start_year)


def _next_frontier(
    timeline: list[Entry],
    current_frontier_id: str,
    stories: list[StarStory] | None = None,
) -> str:
    """Return the next entry_id to grill (most-recent + most-substantive first).

    Strategy: among entries that still need work, skipping the currently-grilled one, pick
    the highest-ranked by :func:`_frontier_sort_key` — current/recent substantive roles
    before older or trivial ones. Returns "" if nothing is left to grill.

    **Coverage steers this (CQ-5b).** An entry used to stop needing work the moment its status
    became GRILLED — which happens after ONE validated story — so a user who uploaded a résumé
    with a dozen strong bullets got one interrogated and eleven silently ignored. Now an entry
    still needs work while ANY of its bullets is uncovered (see :mod:`web.coverage`).

    This is only SAFE because of the ``answers_bullet_id`` link (v2.11.0): the grill records
    which bullet it is asking about, and the resulting story retires exactly that bullet, so
    every successful turn makes progress **by construction**. The earlier text-matching version
    could not guarantee that — a story worded so as to match no bullet advanced nothing, the
    frontier stayed put, and the grill would have asked forever. ``skipped`` remains the escape
    hatch for a line the user simply does not care about.

    ``stories`` is optional so existing callers keep working; without it, coverage cannot be
    computed and the status-only rule applies.
    """
    def _needs_work(entry: Entry) -> bool:
        if str(entry.entry_id) == current_frontier_id:
            return False
        if stories is None:  # legacy callers: status-only
            return entry.status in (EntryStatus.NEEDS_QUANTIFYING, EntryStatus.DOCUMENTED)
        return entry_still_needs_grilling(entry, stories_for(entry, stories))

    needs_work = [e for e in timeline if _needs_work(e)]
    if not needs_work:
        return ""
    needs_work.sort(key=_frontier_sort_key, reverse=True)
    return str(needs_work[0].entry_id)


def _get_frontier_entry(state: CareerEngineState) -> Entry | None:
    """Return the Entry currently pointed to by grill_frontier.

    If grill_frontier is empty, picks the most-recent ungrilled entry.
    If no ungrilled entry exists, returns None.
    """
    # COVERAGE (CQ-5b): this gate was status-only, so it REFUSED a GRILLED entry that still
    # had uncovered lines — the pinned frontier was silently ignored and a different entry was
    # auto-picked. That made "Grill me about this" a no-op on exactly the entries the coverage
    # UI was telling the user to come back to.
    if state.grill_frontier:
        entry = _find_entry_by_id(state.work_timeline, state.grill_frontier)
        if entry is not None and entry_still_needs_grilling(
            entry,
            stories_for(entry, state.extracted_star_stories),
            explicit=True,  # the user pinned it — honour that over the legacy grandfather
        ):
            return entry

    needs_work = [
        e
        for e in state.work_timeline
        if entry_still_needs_grilling(e, stories_for(e, state.extracted_star_stories))
    ]
    if not needs_work:
        return None
    needs_work.sort(key=_frontier_sort_key, reverse=True)
    return needs_work[0]


def _update_entry_in_timeline(
    timeline: list[Entry], updated_entry: Entry
) -> list[Entry]:
    """Return a new timeline list with the updated entry replacing the old one."""
    return [
        updated_entry if str(e.entry_id) == str(updated_entry.entry_id) else e
        for e in timeline
    ]


def _latest_end_date(timeline: list[Entry]) -> str:
    """Return the latest (max) end_date across the timeline.

    An empty end_date means 'present' and wins outright (returns "").  Returns
    "" when the timeline is empty or no entry has a parseable end_date.
    """
    if not timeline:
        return ""
    best_year: int | None = None
    best_date = ""
    for entry in timeline:
        if not entry.end_date:
            return ""  # a 'present' role is the freshest boundary
        year = _parse_year_from_date(entry.end_date)
        if year is not None and (best_year is None or year > best_year):
            best_year = year
            best_date = entry.end_date
    return best_date


_PROCESSED_STATUSES = (
    EntryStatus.GRILLED,
    EntryStatus.SUMMARIZED,
    EntryStatus.SKIPPED,
)


def _apply_entry_status_rules(entries: list[Entry], reference_date: str) -> None:
    """Apply soft-horizon and already-quantified-skip rules to fresh entries IN PLACE.

    Intended for freshly-built entries (just parsed/seeded).  Entries that
    already carry progress (grilled / summarized / skipped) are left untouched,
    so a pre-seeded timeline with prior progress is never silently reset.
    - EDUCATION (degrees / certifications / courses) → summarized (recorded as
      context, never deep-grilled for job-style metrics).
    - Soft horizon (end_date > ~15y before reference_date) → summarized.
    - Documented AND already has a metric-bearing bullet → grilled (not re-asked).
    - Otherwise → needs_quantifying.
    """
    for entry in entries:
        if entry.status in _PROCESSED_STATUSES:
            continue  # preserve existing progress
        if entry.type is ExperienceType.EDUCATION:
            # Degrees / certifications / courses are recorded as context, NOT
            # deep-grilled for job-style metrics — "how much cost did you save?"
            # is nonsensical for a course. (Quantifiable work the candidate
            # actually did should be typed project/research, not education.)
            entry.status = EntryStatus.SUMMARIZED
        elif _is_soft_horizon(entry, reference_date):
            entry.status = EntryStatus.SUMMARIZED
        elif entry.status == EntryStatus.DOCUMENTED and _has_metric_bullet(entry):
            entry.status = EntryStatus.GRILLED
        else:
            entry.status = EntryStatus.NEEDS_QUANTIFYING


# ── Node implementations ──────────────────────────────────────────────────────


def ingest_node(state: CareerEngineState, *, _client: ModelClient | None = None) -> CareerEngineState:
    """Seed the work_timeline and set phase=GRILLING.

    Two entry paths converge here (both run once, on the INGESTING turn):

    1. **Vision-preseeded** — when ``state.work_timeline`` is already populated
       (the CLI ran :func:`tools.resume_parser.parse_resume` on the uploaded
       document and seeded the entries into the initial state).  The raw image
       is PII and never reaches this node; only the structured entries do.
    2. **Text fallback** — when no timeline is present, parse
       ``raw_history_text`` with ``INGEST_SYSTEM_PROMPT``.

    Both paths apply soft-horizon + already-quantified rules, derive
    ``coverage_through`` from the latest end_date, and set the initial
    ``grill_frontier``.

    Args:
        state: Input state with either ``work_timeline`` (vision) or
            ``raw_history_text`` (text) populated.

    Returns:
        Updated state with work_timeline finalized, coverage_through and
        grill_frontier set, and current_phase=GRILLING.
    """
    model_id = _resolve_model(Capability.SPEED_FAST)
    if isinstance(model_id, UpgradeRequired):
        # SPEED_FAST is always resolvable in both modes; guard defensively.
        return state

    ref_date = state.reference_date

    # ── Path 1: vision-preseeded timeline (parsed upstream from a document) ──
    if state.work_timeline:
        new_timeline = [e.model_copy() for e in state.work_timeline]
        _apply_entry_status_rules(new_timeline, ref_date)
        coverage = state.coverage_through or _latest_end_date(new_timeline)
        return state.model_copy(
            update={
                "current_phase": PhaseStatus.GRILLING,
                "work_timeline": new_timeline,
                "coverage_through": coverage,
                "grill_frontier": state.grill_frontier
                or _next_frontier(new_timeline, ""),
                "question_count": 0,
            }
        )

    # ── Path 2: text fallback — parse raw_history_text into entries ──────────
    client = _client if _client is not None else _get_model_client()
    raw = state.raw_history_text.strip() or "(no career history provided)"
    response_text = client.generate(
        model_id=model_id,
        system=INGEST_SYSTEM_PROMPT,
        user=raw,
    )
    parsed = _parse_json_response(response_text)

    entries_raw: list[dict[str, Any]] = parsed.get("timeline", [])
    new_timeline = []
    for item in entries_raw:
        try:
            exp_type = ExperienceType(item.get("type", "other"))
        except ValueError:
            exp_type = ExperienceType.OTHER

        entry = Entry(
            type=exp_type,
            title=str(item.get("title", "Untitled")),
            org=str(item.get("org", "")),
            start_date=str(item.get("start_date", "")),
            end_date=str(item.get("end_date", "")),
            source="resume",
            bullets=list(item.get("bullets", [])),
            status=EntryStatus.DOCUMENTED,
        )
        new_timeline.append(entry)

    # Fallback: if model returned nothing useful, create a generic entry
    if not new_timeline:
        new_timeline = [
            Entry(
                type=ExperienceType.OTHER,
                title="Career History",
                source="manual",
                status=EntryStatus.NEEDS_QUANTIFYING,
            )
        ]

    _apply_entry_status_rules(new_timeline, ref_date)

    return state.model_copy(
        update={
            "current_phase": PhaseStatus.GRILLING,
            "work_timeline": new_timeline,
            "coverage_through": state.coverage_through or _latest_end_date(new_timeline),
            "grill_frontier": _next_frontier(new_timeline, ""),
            "question_count": 0,
        }
    )


def discovery_turn_node(state: CareerEngineState, *, _client: ModelClient | None = None) -> CareerEngineState:
    """Confirm coverage_through and discover new roles not on the resume.

    Asks the user to confirm when they last refreshed their resume, and
    to name any work done since then.  Newly named roles are appended
    to work_timeline as Entry(source='discovered', status='needs_quantifying').

    Uses SPEED_FAST capability (conversation-level, not deep extraction).

    Args:
        state: Current session state with pending_user_answer.

    Returns:
        Updated state with new discovered entries in work_timeline, or
        a question asking about coverage (if no pending answer).
    """
    model_id = _resolve_model(Capability.SPEED_FAST)
    if isinstance(model_id, UpgradeRequired):
        return state

    client = _client if _client is not None else _get_model_client()
    user_answer = state.pending_user_answer.strip()

    if user_answer:
        # Parse the answer to extract newly named roles/projects
        parse_context = (
            f"The user was asked about their recent work not yet on their resume.\n"
            f"Their answer: {user_answer}\n\n"
            f"Extract any newly mentioned roles, projects, or engagements.\n"
            f"Return JSON: {{\"entries\": [{{\"title\": \"...\", \"org\": \"...\", "
            f"\"type\": \"full_time|project|other\", \"start_date\": \"...\", "
            f"\"end_date\": \"...\"}}]}}"
        )
        response_text = client.generate(
            model_id=model_id,
            system=DISCOVERY_SYSTEM_PROMPT,
            user=parse_context,
        )
        parsed = _parse_json_response(response_text)
        entries_raw: list[dict[str, Any]] = parsed.get("entries", [])

        new_entries: list[Entry] = []
        for item in entries_raw:
            try:
                exp_type = ExperienceType(item.get("type", "other"))
            except ValueError:
                exp_type = ExperienceType.OTHER

            entry = Entry(
                type=exp_type,
                title=str(item.get("title", "Untitled Role")),
                org=str(item.get("org", "")),
                start_date=str(item.get("start_date", "")),
                end_date=str(item.get("end_date", "")),
                source="discovered",
                status=EntryStatus.NEEDS_QUANTIFYING,
            )
            new_entries.append(entry)

        # Determine coverage_through from existing timeline (ingest_node usually
        # sets it; fall back to the latest end_date for consistency).
        coverage = state.coverage_through or _latest_end_date(state.work_timeline)

        new_timeline = list(state.work_timeline) + new_entries
        new_frontier = state.grill_frontier or _next_frontier(new_timeline, "")

        # The user's answer has been processed: mark the one-shot discovery turn
        # done (so the router won't re-ask) and clear the surfaced question so the
        # loop advances to grill any newly discovered entries (or finalize).
        return state.model_copy(
            update={
                "work_timeline": new_timeline,
                "coverage_through": coverage,
                "grill_frontier": new_frontier,
                "coverage_confirmed": True,
                "pending_user_answer": "",
                "current_question": "",
            }
        )
    else:
        # Ask about coverage
        coverage = state.coverage_through
        last_entries = state.work_timeline[:2]
        context_hint = (
            f"Last known roles: {', '.join(e.title for e in last_entries)}"
            if last_entries
            else "no roles known yet"
        )
        question_context = (
            f"Help the user confirm when they last updated their resume and discover "
            f"any recent roles not yet captured.  {context_hint}.  "
            f"Coverage through: '{coverage or 'unknown'}'.  "
            f"Ask a warm, conversational question about what they've been working on recently."
        )
        question_text = client.generate(
            model_id=model_id,
            system=DISCOVERY_SYSTEM_PROMPT,
            user=question_context,
        )
        # Defensive fallback: never surface an empty question.  An empty
        # current_question would stall the turn-based CLI loop (it advances on a
        # missing question); a concrete prompt keeps the discovery turn live even
        # if the model returns nothing.
        question = question_text.strip() or (
            "What have you been working on since your resume was last updated?"
        )
        return state.model_copy(
            update={
                "current_question": question,
            }
        )


def execute_grill_turn_node(
    state: CareerEngineState,
    *,
    _client: ModelClient | None = None,
) -> CareerEngineState | UpgradeRequired:
    """Ask one probing question and validate the user's answer for concrete metrics.

    Entry-based grilling (v2.0.0): targets the Entry at state.grill_frontier.

    Uses REASONING_HIGH capability with a Chain-of-Thought system prompt:
    decompose claim → demand a metric → plausibility-check → restate as STAR.
    Tone: senior peer over coffee; NEVER says "STAR" to the user.

    Two-step process per call:
    1. If `pending_user_answer` is non-empty, run METRIC_EXTRACTION_PROMPT to
       parse it.  If metrics_found=True, create a StarStory(entry_id=frontier),
       mark the entry status=grilled, advance the frontier.  If metrics_found=False,
       set `current_question` to a follow-up metric question.
    2. If there is no pending answer, generate an opening question for the
       frontier entry and set `current_question`.

    The user-facing question is ALWAYS surfaced via `current_question`; the
    user's answer is ALWAYS read from `pending_user_answer`.  No field is
    overloaded.

    Returns UpgradeRequired (typed), never raises, when either: the registry cannot
    resolve REASONING_HIGH, OR (Free Mode) a single entry accumulates
    ``_MAX_FLASH_GRILL_ATTEMPTS`` failed metric-extraction attempts — the
    Pro-escalation gate, which recommends a Pro reasoning model (BYOK) instead of
    grinding on Flash.  Per-entry failures are tracked in ``state.grill_attempts``
    and reset when that entry yields a validated metric.

    Args:
        state: Current session state.

    Returns:
        Updated CareerEngineState or UpgradeRequired signal.
    """
    model_id_result = _resolve_model(Capability.REASONING_HIGH)
    if isinstance(model_id_result, UpgradeRequired):
        # Registry could not resolve REASONING_HIGH — propagate signal.
        return model_id_result

    model_id: str = model_id_result
    client = _client if _client is not None else _get_model_client()

    # Find the entry to grill
    frontier_entry = _get_frontier_entry(state)
    if frontier_entry is None:
        # No more entries to grill — signal finalize path
        return state.model_copy(
            update={
                "current_phase": PhaseStatus.GRILLING,
                "grill_frontier": "",
                "current_question": "",
            }
        )

    frontier_id = str(frontier_entry.entry_id)
    user_answer = state.pending_user_answer.strip()
    new_question_count = state.question_count + 1

    if user_answer:
        # ── Step 1: try to extract a validated metric ─────────────────────
        entry_context = (
            f"Entry: {frontier_entry.title} at {frontier_entry.org}\n"
            f"Type: {frontier_entry.type.value}\n"
        )
        # Grill memory: accumulate ALL answers for this entry so extraction can
        # assemble a metric given across multiple turns, and the follow-up never
        # re-asks for something already provided.
        accumulated_answers = [*state.grill_answers.get(frontier_id, []), user_answer]
        answers_block = "\n".join(f"- {a}" for a in accumulated_answers)
        extraction_context = (
            f"{entry_context}\n"
            f"User's answers so far (consider ALL of them together):\n{answers_block}"
        )
        extraction_text = client.generate(
            model_id=model_id,
            system=METRIC_EXTRACTION_PROMPT,
            user=extraction_context,
        )
        extracted = _parse_json_response(extraction_text)
        metrics_found: bool = bool(extracted.get("metrics_found", False))
        # A live model may emit JSON `null` for STAR fields it can't fill; `.get(k, "")`
        # returns None in that case (the key IS present), so use `or ""` to coerce
        # null/absent alike to a valid string (StarStory fields are non-nullable str).
        result_text: str = extracted.get("result") or ""

        # Double-check with our own regex (defensive layer)
        if metrics_found and not _contains_real_metric(result_text):
            metrics_found = False

        if metrics_found:
            # ── Commit a validated StarStory ──────────────────────────────
            story = StarStory(
                entry_id=frontier_id,
                # THE LINK (CQ-5b): this story answers the bullet the grill was asking about.
                # Coverage reads this instead of comparing prose, so a successful turn retires
                # exactly one bullet — progress is monotonic BY CONSTRUCTION, which is what makes
                # it safe for the frontier to hold an entry until it is covered.
                answers_bullet_id=state.grill_bullet_frontier,
                pillar=extracted.get("pillar") or frontier_entry.type.value,
                situation=extracted.get("situation") or "",
                task=extracted.get("task") or "",
                action=extracted.get("action") or "",
                result=result_text,
                metrics_validated=True,
            )
            new_stories = [*state.extracted_star_stories, story]

            # Mark the entry as grilled in the timeline
            grilled_entry = Entry(
                entry_id=frontier_entry.entry_id,
                type=frontier_entry.type,
                title=frontier_entry.title,
                org=frontier_entry.org,
                start_date=frontier_entry.start_date,
                end_date=frontier_entry.end_date,
                source=frontier_entry.source,
                bullets=frontier_entry.bullets,
                status=EntryStatus.GRILLED,
            )
            new_timeline = _update_entry_in_timeline(state.work_timeline, grilled_entry)

            # Advance the frontier — but only away from an entry we have actually FINISHED.
            # The story we just committed retired exactly one bullet (via answers_bullet_id),
            # so if the entry still has uncovered lines we stay on it and ask about the next
            # one. Progress is guaranteed, so this cannot loop (CQ-5b).
            mine = stories_for(grilled_entry, new_stories)
            if entry_needs_work(grilled_entry, mine):
                next_fid = frontier_id
            else:
                next_fid = _next_frontier(new_timeline, frontier_id, new_stories)

            # Clear this entry's failed-attempt counter + answer memory on success.
            cleared_attempts = {
                k: v for k, v in state.grill_attempts.items() if k != frontier_id
            }
            cleared_answers = {
                k: v for k, v in state.grill_answers.items() if k != frontier_id
            }

            return state.model_copy(
                update={
                    "extracted_star_stories": new_stories,
                    "work_timeline": new_timeline,
                    "grill_frontier": next_fid,
                    "question_count": new_question_count,
                    "pending_user_answer": "",
                    "current_question": "",
                    "grill_attempts": cleared_attempts,
                    "grill_answers": cleared_answers,
                }
            )
        else:
            # ── Metrics not found ──────────────────────────────────────────
            new_attempts = dict(state.grill_attempts)
            new_attempts[frontier_id] = new_attempts.get(frontier_id, 0) + 1

            # Pro-escalation gate (Free Mode only): once Flash+CoT has failed to
            # surface a metric on this entry past a full checkpoint cycle, escalate
            # rather than grinding indefinitely on Flash.  In BYOK mode
            # REASONING_HIGH already resolves to Pro, so there is nothing to escalate
            # to and we simply keep probing.
            settings = get_settings()
            if (
                settings.access_mode == AccessMode.FREE
                and new_attempts[frontier_id] >= _MAX_FLASH_GRILL_ATTEMPTS
            ):
                return UpgradeRequired(
                    required_capability=Capability.REASONING_HIGH,
                    node_name="execute_grill_turn_node",
                    reason=(
                        f"Flash+CoT could not surface a concrete metric for "
                        f"{frontier_entry.title!r} after {new_attempts[frontier_id]} "
                        "attempts; a Pro reasoning model (BYOK) is recommended to probe "
                        "more deeply."
                    ),
                )

            # Otherwise ask one sharp probing follow-up — with memory of what was
            # already said, so it never re-asks for a number already provided.
            probe_context = (
                f"Entry: {frontier_entry.title} at {frontier_entry.org}\n\n"
                f"What the person has ALREADY told you (do NOT re-ask for any of this):\n"
                f"{answers_block}\n\n"
                f"None of it yet contains a concrete metric.  Ask ONE sharp follow-up for "
                f"a specific NEW number they have not already given.  If they've clearly "
                f"said there is no number to give, acknowledge that and ask whether to move on."
            )
            question_text = client.generate(
                model_id=model_id,
                system=GRILL_SYSTEM_PROMPT,
                user=probe_context,
            )
            new_answers = {**state.grill_answers, frontier_id: accumulated_answers}
            return state.model_copy(
                update={
                    "question_count": new_question_count,
                    "current_question": question_text.strip(),
                    "pending_user_answer": "",
                    "grill_frontier": frontier_id,
                    "grill_attempts": new_attempts,
                    "grill_answers": new_answers,
                }
            )
    else:
        # ── Step 2: generate opening question for the frontier entry ──────
        # COVERAGE (CQ-5b): aim at a SPECIFIC uncovered bullet rather than asking vaguely for
        # "a project or achievement". That vague opener is exactly why a user who uploaded a
        # dozen strong lines got one interrogated and eleven ignored. Recording which bullet we
        # are asking about (grill_bullet_frontier) is also what makes progress monotonic: the
        # answer's story retires THAT bullet, so the frontier can hold the entry until it is
        # covered without any risk of looping.
        target = _next_uncovered_bullet(
            frontier_entry, stories_for(frontier_entry, state.extracted_star_stories)
        )
        if target is not None:
            opening_context = (
                f"You are exploring the '{frontier_entry.title}' role/project at "
                f"'{frontier_entry.org}'.  "
                f"The candidate's résumé claims: \"{target.text}\".  "
                f"Ask ONE question that pushes them to put a concrete NUMBER on that specific "
                f"claim — scale, money, time, or percentage.  Do not ask about anything else."
            )
        else:
            opening_context = (
                f"You are starting to explore the '{frontier_entry.title}' role/project "
                f"at '{frontier_entry.org}'.  "
                f"Ask them to describe a specific project or achievement that shows "
                f"their impact in this role.  "
                f"Keep it open and conversational — one question only."
            )
        question_text = client.generate(
            model_id=model_id,
            system=GRILL_SYSTEM_PROMPT,
            user=opening_context,
        )
        return state.model_copy(
            update={
                "question_count": new_question_count,
                "current_question": question_text.strip(),
                "grill_frontier": frontier_id,
                "grill_bullet_frontier": str(target.bullet_id) if target else "",
            }
        )


def user_checkpoint_node(state: CareerEngineState, *, _client: ModelClient | None = None) -> CareerEngineState:
    """Hydration Point — summarise the last 5-turn delta and await user verification.

    Summarises everything that has been extracted in the most recent batch of
    grill turns.  Does NOT commit or advance to the next phase until
    checkpoint_verified=True.

    In the ADK graph the runner will interrupt here for user input; only when
    the user confirms (setting checkpoint_verified=True externally, e.g. via
    the CLI shim) will the router continue.

    Args:
        state: Current session state.

    Returns:
        State with checkpoint_delta_summary populated and checkpoint_verified
        reset to False (awaiting user confirmation).  If checkpoint_verified
        is already True on entry, the node resets it and advances the phase.
    """
    # If already verified, advance phase and reset for the next batch
    if state.checkpoint_verified:
        return state.model_copy(
            update={
                "checkpoint_verified": False,
                "checkpoint_delta_summary": "",
                "current_phase": PhaseStatus.GRILLING,
            }
        )

    # Build the delta summary from the most recently extracted stories
    model_id = _resolve_model(Capability.SPEED_FAST)
    if isinstance(model_id, UpgradeRequired):
        # Fallback: produce a minimal summary without a model call
        n = len(state.extracted_star_stories)
        grilled_count = sum(
            1 for e in state.work_timeline if e.status == EntryStatus.GRILLED
        )
        summary = (
            f"So far we've captured {n} achievement(s) across {grilled_count} role(s).  "
            "Does everything sound accurate before we continue?"
        )
        return state.model_copy(
            update={
                "checkpoint_delta_summary": summary,
                "checkpoint_verified": False,
                "current_phase": PhaseStatus.CHECKPOINT,
            }
        )

    client = _client if _client is not None else _get_model_client()

    # Summarise recent stories (last 5 or all if fewer)
    recent_stories = state.extracted_star_stories[-5:]
    stories_text = "\n\n".join(
        f"- {s.pillar}: {s.result}" if s.result else f"- {s.pillar}: (no metric yet)"
        for s in recent_stories
    )
    if not stories_text:
        stories_text = "(no achievements captured yet in this batch)"

    pending_count = sum(
        1 for e in state.work_timeline
        if e.status in (EntryStatus.NEEDS_QUANTIFYING, EntryStatus.DOCUMENTED)
    )
    summary_input = (
        f"Recent achievements (last batch):\n{stories_text}\n\n"
        f"Total achievements captured so far: {len(state.extracted_star_stories)}\n"
        f"Remaining entries to explore: {pending_count}"
    )

    summary_text = client.generate(
        model_id=model_id,
        system=CHECKPOINT_SUMMARY_PROMPT,
        user=summary_input,
    )

    return state.model_copy(
        update={
            "checkpoint_delta_summary": summary_text.strip(),
            "checkpoint_verified": False,
            "current_phase": PhaseStatus.CHECKPOINT,
        }
    )


def finalize_master_resume_node(state: CareerEngineState, *, _client: ModelClient | None = None) -> CareerEngineState:
    """Assemble all validated StarStories into the master resume structure.

    Uses SPEED_FAST capability (Flash baseline).  Sends the validated stories
    to FINALIZE_SYSTEM_PROMPT to produce a structured resume JSON.  Writes:
      - `master_resume_json`: the structured resume JSON.
      - `professional_summary`: the prose summary (pdf_renderer reads THIS).
    Sets current_phase to COMPLETE.

    Args:
        state: State with validated extracted_star_stories.

    Returns:
        State with current_phase=COMPLETE, master_resume_json populated, and
        professional_summary set to a prose summary.
    """
    model_id = _resolve_model(Capability.SPEED_FAST)
    if isinstance(model_id, UpgradeRequired):
        return state.model_copy(update={"current_phase": PhaseStatus.COMPLETE})

    client = _client if _client is not None else _get_model_client()

    stories_payload = [
        {
            "pillar": s.pillar,
            "entry_id": s.entry_id,
            "situation": s.situation,
            "task": s.task,
            "action": s.action,
            "result": s.result,
        }
        for s in state.extracted_star_stories
        if s.metrics_validated
    ]

    finalize_input = json.dumps({"validated_achievements": stories_payload}, indent=2)
    resume_json_text = client.generate(
        model_id=model_id,
        system=FINALIZE_SYSTEM_PROMPT,
        user=finalize_input,
    )

    # Extract the prose summary from the structured output so the PDF renderer
    # has a real professional_summary to display.  Fall back gracefully if the
    # model output is not parseable JSON.
    parsed = _parse_json_response(resume_json_text)
    summary = str(parsed.get("summary", "")).strip()

    return state.model_copy(
        update={
            "current_phase": PhaseStatus.COMPLETE,
            "master_resume_json": resume_json_text.strip(),
            "professional_summary": summary,
        }
    )


def tailor_node(state: CareerEngineState, *, _client: ModelClient | None = None, _instructions: str = "") -> CareerEngineState:
    """Produce a targeted resume variant from a cleaned job description.

    Uses SPEED_FAST capability (Flash baseline).  Reads:
      - the cleaned JD from `jd_text`,
      - the master resume from `master_resume_json`.
    Writes the result to `tailored_resume_json`.

    Args:
        state: State with current_phase=COMPLETE, master_resume_json populated,
               and jd_text set to the cleaned job description.

    Returns:
        State with tailored_resume_json populated.
    """
    model_id = _resolve_model(Capability.SPEED_FAST)
    if isinstance(model_id, UpgradeRequired):
        return state

    client = _client if _client is not None else _get_model_client()

    master_resume = state.master_resume_json
    jd_text = state.jd_text.strip() or "(no job description provided)"

    tailor_input = (
        f"MASTER RESUME:\n{master_resume}\n\n"
        f"JOB DESCRIPTION (cleaned):\n{jd_text}"
    )

    stripped_instructions = _instructions.strip()
    extra = (
        f"\n\n[Additional instructions — apply to this résumé only]:\n{stripped_instructions}"
        if stripped_instructions else ""
    )
    effective_user = tailor_input + extra
    tailored_text = client.generate(
        model_id=model_id,
        system=TAILOR_SYSTEM_PROMPT,
        user=effective_user,
    )

    return state.model_copy(
        update={
            "tailored_resume_json": tailored_text.strip(),
        }
    )
