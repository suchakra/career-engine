"""CareerEngine Pydantic v2 schema — contract v2.0.0 (Phase 1.5 BREAKING change).

Every value that crosses a boundary (agent→agent, agent→database, agent→UI)
must be an instance of one of these models.  Free-text hand-offs are forbidden.

Design rules (enforced by the Definition of Done):
- CareerEngineState carries NO secrets, NO UI state, and NO identity.
  user_id travels via the ADK session/context, never inside the state object.
- Every model is round-trip serializable via model_dump_json() / model_validate_json().
- CONTRACT_VERSION is stamped on every envelope so consumers can detect major
  schema breaks and refuse rather than mis-parse.
- reference_date (ISO date string) is the INJECTED clock — nodes NEVER call
  datetime.now(); the CLI/entry layer stamps it for determinism and testability.
- Pillar fields (target_competencies, active_gaps, current_pillar) are REMOVED
  in v2.0.0; replaced by work_timeline + grill_frontier.

v2.0.0 change summary:
  - Added Entry model (ExperienceType enum, EntryStatus enum).
  - Added work_timeline, coverage_through, reference_date, grill_frontier to
    CareerEngineState.
  - Removed target_competencies, active_gaps, current_pillar from
    CareerEngineState.
  - Added entry_id to StarStory (links a story to its Entry).
  - Added discovery_completeness() and recent_window_complete() pure helpers.

v2.3.0 change summary (additive, backward-compatible):
  - Added grill_attempts (dict[str, int]) to CareerEngineState — per-entry failed
    metric-extraction counter driving the Free-Mode Pro-escalation gate.

v2.4.0 change summary (additive, backward-compatible):
  - Added grill_answers (dict[str, list[str]]) to CareerEngineState — per-entry
    running list of the user's answers, giving the grill loop memory (accumulated
    extraction + no re-asking).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from config import CONTRACT_VERSION

# ── Enums ─────────────────────────────────────────────────────────────────────


class Capability(StrEnum):
    """Model capability tier requested by a workflow node.

    Features declare the capability they need; the registry resolves this to the
    best available model for the current access mode.  No feature code ever names
    a model directly.
    """

    REASONING_HIGH = "reasoning_high"
    """Multi-step extraction, metric validation — opt-in paid tier in BYOK mode."""

    SPEED_FAST = "speed_fast"
    """Summaries, tailoring, checkpoint synthesis — Flash baseline."""

    BULK_CHEAP = "bulk_cheap"
    """Scrape cleanup, bulk parsing — Flash-Lite baseline."""


class PhaseStatus(StrEnum):
    """Lifecycle phase of a CareerEngine discovery session."""

    INGESTING = "ingesting"
    GRILLING = "grilling"
    CHECKPOINT = "checkpoint"
    FINALIZING = "finalizing"
    COMPLETE = "complete"


class ExperienceType(StrEnum):
    """Type of career experience entry being tracked."""

    FULL_TIME = "full_time"
    INTERNSHIP = "internship"
    PROJECT = "project"
    RESEARCH = "research"
    OPEN_SOURCE = "open_source"
    LEADERSHIP = "leadership"
    PART_TIME = "part_time"
    EDUCATION = "education"
    OTHER = "other"


class EntryStatus(StrEnum):
    """Processing status of an experience entry in the discovery pipeline."""

    DOCUMENTED = "documented"
    """Entry has bullets but metrics have not yet been quantified/validated."""

    NEEDS_QUANTIFYING = "needs_quantifying"
    """Entry is present but lacks quantified bullets; scheduled for grilling."""

    GRILLED = "grilled"
    """Entry has been conversationally grilled and has a validated StarStory."""

    SUMMARIZED = "summarized"
    """Entry is old enough (soft horizon) to be summarized, not deep-grilled."""

    SKIPPED = "skipped"
    """Entry was explicitly skipped by the user."""


# ── Core domain models ────────────────────────────────────────────────────────


class Entry(BaseModel):
    """A single career experience entry in the work timeline.

    The grillable unit of discovery: a job, internship, project, research
    engagement, open-source contribution, leadership role, or education item.
    """

    model_config = ConfigDict(frozen=False)

    entry_id: UUID = Field(
        default_factory=uuid4,
        description="Stable identifier for this entry (UUID)",
    )
    type: ExperienceType = Field(
        default=ExperienceType.OTHER,
        description="Category of experience (full_time, project, education, etc.)",
    )
    title: str = Field(
        description="Role/project title (e.g. 'Senior Engineer', 'Capstone Project')"
    )
    org: str = Field(
        default="",
        description="Organisation, school, or team name",
    )
    start_date: str = Field(
        default="",
        description="Start date in YYYY-MM or YYYY format; empty means unknown",
    )
    end_date: str = Field(
        default="",
        description="End date in YYYY-MM or YYYY format; empty string means 'present'",
    )
    source: Literal["resume", "discovered", "manual"] = Field(
        default="manual",
        description="How this entry entered the timeline",
    )
    bullets: list[str] = Field(
        default_factory=list,
        description="Existing resume bullets or notes for this entry",
    )
    status: EntryStatus = Field(
        default=EntryStatus.NEEDS_QUANTIFYING,
        description="Processing status of this entry in the discovery pipeline",
    )
    highlighted: bool = Field(
        default=False,
        description=(
            "User pinned this experience as tailoring priority (4E, additive v2.7.0): "
            "its quantified achievements are always included when tailoring to a JD."
        ),
    )


class StarStory(BaseModel):
    """A single STAR-formatted career achievement extracted during the grill loop.

    The agent never mentions "STAR" to the user; internally we structure every
    achievement in this format and validate that a real metric is present before
    setting metrics_validated=True.
    """

    model_config = ConfigDict(frozen=True)

    story_id: UUID = Field(default_factory=uuid4, description="Stable identifier for this story")
    entry_id: str = Field(
        default="",
        description="UUID string of the Entry this story is linked to (v2.0.0+)",
    )
    pillar: str = Field(description="Career pillar / competency tag (e.g. 'leadership')")
    situation: str = Field(default="", description="Context / situation (S in STAR)")
    task: str = Field(default="", description="Task or responsibility (T in STAR)")
    action: str = Field(default="", description="Actions taken (A in STAR)")
    result: str = Field(default="", description="Quantified outcome (R in STAR; must contain a metric)")
    metrics_validated: bool = Field(
        default=False,
        description="True only when result contains at least one concrete numeric metric",
    )
    extracted_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp when this story was extracted",
    )


class CareerEngineState(BaseModel):
    """The single shared state object threaded through every workflow node.

    Strict rules:
    - NO secrets (API keys, tokens, passwords)
    - NO UI state (widget state, cursor positions, display flags)
    - NO identity (user_id is passed via the ADK session/context, not here)

    This object IS the contract between all workflow nodes.  Its shape may only
    change with a CONTRACT_VERSION bump.

    v2.0.0: pillar fields (target_competencies, active_gaps, current_pillar)
    replaced by entry-based timeline (work_timeline, grill_frontier).
    reference_date is the injected clock; nodes must NEVER call datetime.now().
    """

    model_config = ConfigDict(frozen=False)  # mutable during a session

    # ── Discovery progress ────────────────────────────────────────────────────
    current_phase: PhaseStatus = Field(
        default=PhaseStatus.INGESTING,
        description="Current lifecycle phase of the session",
    )

    # ── Work timeline (v2.0.0) ────────────────────────────────────────────────
    work_timeline: list[Entry] = Field(
        default_factory=list,
        description="Ordered list of career experience entries (newest first by convention)",
    )
    coverage_through: str = Field(
        default="",
        description="Latest end_date confirmed by the user; freshness boundary for discovery",
    )
    reference_date: str = Field(
        default="",
        description=(
            "ISO date (YYYY-MM-DD) injected by the CLI/entry layer as the 'now' clock. "
            "Nodes must NEVER call datetime.now(); use this field instead."
        ),
    )
    grill_frontier: str = Field(
        default="",
        description=(
            "entry_id (UUID string) of the entry currently being grilled, or the last "
            "grilled entry.  Advances backward-chronologically as entries are completed.  "
            "Jumpable: setting it explicitly targets that entry next."
        ),
    )
    coverage_confirmed: bool = Field(
        default=False,
        description=(
            "True once the discovery turn has run and the user has confirmed/added "
            "work since coverage_through (v2.1.0).  Records that the one-shot "
            "discovery turn is done so the router does not re-ask it."
        ),
    )

    # ── Extracted content ─────────────────────────────────────────────────────
    extracted_star_stories: list[StarStory] = Field(
        default_factory=list,
        description="All STAR stories validated so far in this session",
    )
    raw_history_text: str = Field(
        default="",
        description="Raw career history as provided by the user (ephemeral; not persisted long-term)",
    )

    # ── Conversation counters ─────────────────────────────────────────────────
    question_count: int = Field(
        default=0,
        ge=0,
        description="Total grill questions asked; drives the 5-turn checkpoint brake",
    )
    grill_attempts: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "Per-entry count of failed metric-extraction attempts (entry_id → count), "
            "added in v2.3.0.  Drives the Free-Mode Pro-escalation gate: once an entry "
            "accumulates too many Flash+CoT failures, the grill node emits UpgradeRequired "
            "recommending a Pro reasoning model.  Reset for an entry on a validated answer."
        ),
    )
    grill_answers: dict[str, list[str]] = Field(
        default_factory=dict,
        description=(
            "Per-entry running list of the user's answers for the entry being grilled "
            "(entry_id → [answer, ...]), added in v2.4.0.  Gives the grill loop memory: "
            "metric extraction sees ALL answers for an entry (so a number given across "
            "turns assembles), and the follow-up question avoids re-asking for something "
            "already provided.  Cleared for an entry once it yields a validated metric."
        ),
    )

    # ── Checkpoint state ──────────────────────────────────────────────────────
    checkpoint_delta_summary: str = Field(
        default="",
        description="Summary of the last 5-turn delta, generated by the checkpoint node",
    )
    checkpoint_verified: bool = Field(
        default=False,
        description="True once the user has confirmed the checkpoint delta",
    )

    # ── Conversational turn buffer (added in v1.1.0, carried forward) ─────────
    pending_user_answer: str = Field(
        default="",
        description="The user's most recent answer awaiting metric extraction; cleared once processed",
    )
    current_question: str = Field(
        default="",
        description="The question the agent wants to surface to the user this turn",
    )

    # ── Final outputs (added in v1.1.0, carried forward) ─────────────────────
    professional_summary: str = Field(
        default="",
        description="Prose professional summary for the rendered resume (set by finalize)",
    )
    master_resume_json: str = Field(
        default="",
        description="Structured master-resume JSON produced by the finalize node",
    )
    tailored_resume_json: str = Field(
        default="",
        description="Structured tailored-resume JSON produced by the tailor node",
    )
    jd_text: str = Field(
        default="",
        description="Cleaned job-description text used as input to the tailor node",
    )

    # ── Contract stamp ────────────────────────────────────────────────────────
    contract_version: str = Field(
        default=CONTRACT_VERSION,
        description="Schema version; consumers refuse on major-version mismatch",
    )


# ── Application tracking & per-user workspace (v2.2.0) ────────────────────────
#
# UserWorkspace is the PER-USER portfolio document (keyed by user_id in the
# persistence layer — identity travels via session/context, not stored here),
# distinct from the per-discovery-session CareerEngineState. It holds tracked
# job applications and the pending-action markers the async sweep writes (§8).


class ApplicationStatus(StrEnum):
    """Lifecycle status of a tracked job application."""

    APPLIED = "applied"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class Application(BaseModel):
    """A single tracked job application (no secrets/PII beyond what the user enters)."""

    model_config = ConfigDict(frozen=False)

    application_id: UUID = Field(default_factory=uuid4, description="Stable identifier")
    company: str = Field(default="", description="Employer / organisation name")
    job_title: str = Field(default="", description="Role title applied for")
    status: ApplicationStatus = Field(
        default=ApplicationStatus.APPLIED,
        description="Application lifecycle status",
    )
    applied_on: str = Field(
        default="",
        description=(
            "ISO date (YYYY-MM-DD) the application was submitted; set at the "
            "boundary, never via datetime.now() in logic. Drives the 14-day sweep."
        ),
    )
    jd_text: str = Field(
        default="",
        description="Cleaned job-description text this application was tailored against",
    )
    tailored_resume_json: str = Field(
        default="",
        description="The tailored resume variant used for this application (JSON)",
    )


class PendingAction(BaseModel):
    """A follow-up marker the async sweep writes onto a user's workspace (§8)."""

    model_config = ConfigDict(frozen=False)

    action_id: UUID = Field(default_factory=uuid4, description="Stable identifier")
    application_id: str = Field(
        default="",
        description="UUID string of the Application this action refers to",
    )
    kind: str = Field(
        default="follow_up",
        description="Action type (e.g. 'follow_up')",
    )
    reason: str = Field(
        default="",
        description="Human-readable reason surfaced in the dashboard",
    )
    created_on: str = Field(
        default="",
        description="ISO date the marker was created (injected clock, not datetime.now())",
    )


class UserProfile(BaseModel):
    """The user's résumé-header identity, persisted so it isn't re-entered.

    Sourced from what the user types in the Tailor contact form (and, later, from
    résumé parsing). Contains only self-provided contact details — no secrets, no
    BYOK key. Optional/empty for a new user.
    """

    model_config = ConfigDict(frozen=False)

    name: str = Field(default="", description="Full name for the résumé header")
    email: str = Field(default="", description="Contact email")
    phone: str = Field(default="", description="Contact phone")
    location: str = Field(default="", description="Location string (e.g. 'Remote · US')")
    links: list[str] = Field(
        default_factory=list, description="Profile links (LinkedIn, GitHub, portfolio)"
    )
    contract_version: str = Field(default=CONTRACT_VERSION)


class UserWorkspace(BaseModel):
    """Per-user portfolio document: tracked applications + pending actions + profile.

    Persisted keyed by user_id (identity via context, per the contract rule —
    not stored on the model). Stamped with CONTRACT_VERSION like every
    persisted document; consumers refuse on major-version mismatch.
    """

    model_config = ConfigDict(frozen=False)

    applications: list[Application] = Field(
        default_factory=list,
        description="All job applications the user is tracking",
    )
    pending_actions: list[PendingAction] = Field(
        default_factory=list,
        description="Outstanding follow-up markers (written by the async sweep)",
    )
    profile: UserProfile = Field(
        default_factory=UserProfile,
        description="Persisted résumé-header identity (additive v2.6.0)",
    )
    # Forward-ref to SessionPreferences (defined later in the discovery section);
    # UserWorkspace.model_rebuild() is called right after that class to resolve it.
    discovery_preferences: SessionPreferences = Field(
        default_factory=lambda: SessionPreferences(),
        description="Persisted job-discovery rubric (additive v2.8.0)",
    )
    contract_version: str = Field(
        default=CONTRACT_VERSION,
        description="Schema version; consumers refuse on major-version mismatch",
    )


# ── Derived pure helpers (NOT stored) ────────────────────────────────────────


def _parse_year(date_str: str) -> int | None:
    """Extract the year from a YYYY-MM or YYYY date string; return None on failure."""
    if not date_str:
        return None
    try:
        return int(date_str.split("-")[0])
    except (ValueError, IndexError):
        return None


def discovery_completeness(state: CareerEngineState) -> float:
    """Return the fraction of trailing-5-year-window entries that are grilled/summarized.

    Uses state.reference_date as 'now' — NEVER calls datetime.now().
    Returns 0.0 if reference_date is not set or there are no entries in the window.
    The 5-year window is a lookback nudge metric, NOT a gate.
    """
    ref_year = _parse_year(state.reference_date)
    if ref_year is None:
        return 0.0

    cutoff_year = ref_year - 5
    window_entries = []
    for entry in state.work_timeline:
        # An entry with empty end_date is "present" — always in the window
        if not entry.end_date:
            window_entries.append(entry)
            continue
        end_year = _parse_year(entry.end_date)
        if end_year is not None and end_year >= cutoff_year:
            window_entries.append(entry)

    if not window_entries:
        return 0.0

    done = sum(
        1
        for e in window_entries
        if e.status in (EntryStatus.GRILLED, EntryStatus.SUMMARIZED, EntryStatus.SKIPPED)
    )
    return done / len(window_entries)


def recent_window_complete(state: CareerEngineState) -> bool:
    """Return True if the trailing-5-year window has >= 1 validated entry and no needs_quantifying.

    A window is 'complete' for nudge/meter purposes when all window entries
    have been processed (no NEEDS_QUANTIFYING left) AND at least one entry
    is grilled (has a validated story).  Uses state.reference_date — NEVER
    calls datetime.now().  Does NOT gate anything.
    """
    ref_year = _parse_year(state.reference_date)
    if ref_year is None:
        return False

    cutoff_year = ref_year - 5
    window_entries = []
    for entry in state.work_timeline:
        if not entry.end_date:
            window_entries.append(entry)
            continue
        end_year = _parse_year(entry.end_date)
        if end_year is not None and end_year >= cutoff_year:
            window_entries.append(entry)

    if not window_entries:
        return False

    has_validated = any(e.status == EntryStatus.GRILLED for e in window_entries)
    has_unprocessed = any(
        e.status in (EntryStatus.NEEDS_QUANTIFYING, EntryStatus.DOCUMENTED)
        for e in window_entries
    )
    return has_validated and not has_unprocessed


# ── Inter-agent message envelope ──────────────────────────────────────────────


class AgentMessage(BaseModel):
    """Typed envelope for every inter-agent and cross-boundary message.

    All node-to-node handoffs MUST use this envelope so that:
    - The contract_version is always present and checkable.
    - The payload is always a validated Pydantic model (never free-text).
    - Consumers can detect schema breaks before attempting to parse payload.
    """

    model_config = ConfigDict(frozen=True)

    message_id: UUID = Field(default_factory=uuid4, description="Unique message identifier")
    contract_version: str = Field(
        default=CONTRACT_VERSION,
        description="CONTRACT_VERSION at the time this message was emitted",
    )
    sender: str = Field(description="Name of the emitting node or service")
    recipient: str = Field(description="Name of the intended receiving node or service")
    payload: dict[str, Any] = Field(
        description="Serialized payload (always model_dump() of a Pydantic model)"
    )
    payload_type: str = Field(
        description="Fully-qualified class name of the Pydantic model in payload"
    )
    emitted_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp of emission",
    )


# ── Upgrade signal ────────────────────────────────────────────────────────────


class UpgradeRequired(BaseModel):
    """Typed signal returned when a REASONING_HIGH task cannot be satisfied in Free Mode.

    Workflow nodes MUST return this model (never raise) when the capability
    required is not available for the current access mode.  The UI layer
    surfaces a specific, actionable message; the graph routes without crashing.
    """

    model_config = ConfigDict(frozen=True)

    contract_version: str = Field(
        default=CONTRACT_VERSION,
        description="CONTRACT_VERSION at the time this signal was emitted",
    )
    required_capability: Capability = Field(
        description="The capability that could not be satisfied"
    )
    node_name: str = Field(description="Name of the workflow node that emitted this signal")
    reason: str = Field(
        description="Human-readable explanation of why the capability shortfall occurred"
    )
    user_message: str = Field(
        default=(
            "This task requires advanced reasoning. "
            "Please provide your Gemini API key or upgrade to BYOK mode to continue."
        ),
        description="Ready-to-display message for the UI layer",
    )
    emitted_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp of signal emission",
    )


# ── Discovery: two-agent (A2A) job sourcing ontology (v2.5.0) ─────────────────
#
# The typed contract for the decoupled Primary (stateful Groomer/Tailor) ⇄ Scout
# (stateless Fetcher) loop. The Scout fetches JobOpportunity objects via the MCP
# server; the Primary evaluates them against the user's preferences + ledger and
# returns an EvaluationDiff (accepted / soft-rejected + the next Scout directive).
# All inter-agent messages are validated Pydantic models — never free-text — so the
# A2A boundary stays clean whether the transport is in-process or the A2A protocol.


class WorkModel(StrEnum):
    """Where a role is performed (a common hard dealbreaker axis)."""

    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class EmploymentType(StrEnum):
    """Engagement type of a job posting (fractional/contract vs W2 full-time)."""

    FULL_TIME = "full_time"
    CONTRACT = "contract"
    FRACTIONAL = "fractional"
    PART_TIME = "part_time"
    UNKNOWN = "unknown"


class MatchStatus(StrEnum):
    """The Primary Agent's classification of a job against the user's rubric."""

    ACCEPTED = "accepted"
    """Matches all core criteria."""
    SOFT_REJECT = "soft_reject"
    """Fails a preference but is not a dealbreaker — kept for user review."""
    HARD_REJECT = "hard_reject"
    """Violates the ledger (already applied) or an absolute dealbreaker — dropped."""


class ScoutBatchStatus(StrEnum):
    """The Primary's verdict on a batch, carried on the EvaluationDiff."""

    APPROVE_BATCH = "approve_batch"
    PARTIAL_ACCEPT = "partial_accept"
    REJECT_BATCH = "reject_batch"


class SessionPreferences(BaseModel):
    """The evaluation rubric for a discovery session (gathered at intake).

    ``dealbreakers`` are absolute (→ HARD_REJECT); ``nice_to_haves`` are soft
    (a miss → SOFT_REJECT, kept for review). No secrets. Persisted per user on
    ``UserWorkspace.discovery_preferences`` (v2.8.0) so it isn't re-entered.
    """

    model_config = ConfigDict(frozen=False)

    target_roles: list[str] = Field(default_factory=list, description="Roles being targeted this session")
    dealbreakers: list[str] = Field(
        default_factory=list, description="Absolute exclusions (e.g. 'W2 only', 'on-site', 'no cloud')"
    )
    nice_to_haves: list[str] = Field(
        default_factory=list, description="Soft preferences (a miss is a SOFT_REJECT, not a drop)"
    )
    contract_version: str = Field(default=CONTRACT_VERSION)


# Resolve the forward reference in UserWorkspace.discovery_preferences now that
# SessionPreferences is defined (see UserWorkspace above).
UserWorkspace.model_rebuild()


class InteractionLedger(BaseModel):
    """Historical state that gates duplicate processing (hydrated from the workspace).

    Enables idempotent HARD_REJECT of jobs the user already applied to or companies
    they've dismissed, so the background loop never re-surfaces them.
    """

    model_config = ConfigDict(frozen=False)

    already_applied_ids: list[str] = Field(
        default_factory=list, description="job_ids already applied to (HARD_REJECT on match)"
    )
    rejected_companies: list[str] = Field(
        default_factory=list, description="Companies the user has dismissed (case-insensitive match)"
    )
    contract_version: str = Field(default=CONTRACT_VERSION)


class JobMetadata(BaseModel):
    """Structured, filterable facts about a posting (separate from the raw text)."""

    model_config = ConfigDict(frozen=False)

    title: str = Field(default="", description="Role title")
    company: str = Field(default="", description="Hiring organisation")
    work_model: WorkModel = Field(default=WorkModel.UNKNOWN)
    employment_type: EmploymentType = Field(default=EmploymentType.UNKNOWN)
    location: str = Field(default="", description="Location string, if any")
    url: str = Field(default="", description="Source URL of the posting")


class JobOpportunity(BaseModel):
    """A fetched job posting — the Scout's output and the DB ledger entity.

    ``job_id`` is a stable content hash (source + external id) for **idempotency**:
    the background worker can crash/restart without duplicating records. The Primary
    fills ``match_status`` + ``ai_rationale`` during evaluation (empty from the Scout).
    """

    model_config = ConfigDict(frozen=False)

    job_id: str = Field(description="Stable idempotency hash (source + external id)")
    metadata: JobMetadata = Field(default_factory=JobMetadata)
    raw_description: str = Field(default="", description="Full JD text payload")
    match_status: MatchStatus | None = Field(
        default=None, description="Set by the Primary Agent during evaluation"
    )
    ai_rationale: str = Field(
        default="", description="Primary Agent's one-line explanation of the classification"
    )
    contract_version: str = Field(default=CONTRACT_VERSION)


class ScoutDirective(BaseModel):
    """A structured search instruction from the Primary to the (stateless) Scout.

    Structured (not free prose) so refinement across loop iterations is deterministic
    and testable. Every directive is self-contained — the Scout keeps no memory.
    """

    model_config = ConfigDict(frozen=False)

    query: str = Field(default="", description="Free-text search query / role focus")
    include_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    exclude_companies: list[str] = Field(default_factory=list)
    desired_count: int = Field(default=5, ge=1, description="Target number of fresh matches")
    adjustment_note: str = Field(
        default="", description="Human-readable steer for the next fetch (e.g. 'drop Director, add fractional')"
    )
    contract_version: str = Field(default=CONTRACT_VERSION)


class EvaluationDiff(BaseModel):
    """The Primary Agent's A2A response for one loop iteration.

    Carries the classified batch (accepted + soft-rejected are persisted; hard-rejects
    are dropped) plus the ``next_directive`` for the Scout when the quota is unmet.
    ``next_directive is None`` signals the loop is satisfied and terminates.
    """

    model_config = ConfigDict(frozen=False)

    status: ScoutBatchStatus = Field(description="Verdict on this batch")
    accepted_jobs: list[JobOpportunity] = Field(default_factory=list)
    soft_rejected_jobs: list[JobOpportunity] = Field(default_factory=list)
    next_directive: ScoutDirective | None = Field(
        default=None, description="Refined directive for the next fetch; None → loop done"
    )
    contract_version: str = Field(default=CONTRACT_VERSION)


def make_job_id(source: str, external_id: str) -> str:
    """Stable idempotency hash for a posting: sha256(source|external_id), 16 hex chars.

    Same posting → same id across worker restarts, so the ledger never dupes.
    """
    digest = hashlib.sha256(f"{source.strip().lower()}|{external_id.strip()}".encode()).hexdigest()
    return digest[:16]
