"""CareerEngine Pydantic v2 schema — the frozen Phase-0 contract.

Every value that crosses a boundary (agent→agent, agent→database, agent→UI)
must be an instance of one of these models.  Free-text hand-offs are forbidden.

Design rules (enforced by the Definition of Done):
- CareerEngineState carries NO secrets, NO UI state, and NO identity.
  user_id travels via the ADK session/context, never inside the state object.
- Every model is round-trip serializable via model_dump_json() / model_validate_json().
- CONTRACT_VERSION is stamped on every envelope so consumers can detect major
  schema breaks and refuse rather than mis-parse.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
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


# ── Core domain models ────────────────────────────────────────────────────────


class StarStory(BaseModel):
    """A single STAR-formatted career achievement extracted during the grill loop.

    The agent never mentions "STAR" to the user; internally we structure every
    achievement in this format and validate that a real metric is present before
    setting metrics_validated=True.
    """

    model_config = ConfigDict(frozen=True)

    story_id: UUID = Field(default_factory=uuid4, description="Stable identifier for this story")
    pillar: str = Field(description="Career pillar / competency this story belongs to (e.g. 'leadership')")
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
    """

    model_config = ConfigDict(frozen=False)  # mutable during a session

    # ── Discovery progress ────────────────────────────────────────────────────
    current_phase: PhaseStatus = Field(
        default=PhaseStatus.INGESTING,
        description="Current lifecycle phase of the session",
    )
    current_pillar: str = Field(
        default="",
        description="Career pillar currently being explored (e.g. 'technical leadership')",
    )
    target_competencies: list[str] = Field(
        default_factory=list,
        description="Ordered list of competency pillars to work through",
    )
    active_gaps: list[str] = Field(
        default_factory=list,
        description="Pillars where no validated StarStory has been extracted yet",
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

    # ── Checkpoint state ──────────────────────────────────────────────────────
    checkpoint_delta_summary: str = Field(
        default="",
        description="Summary of the last 5-turn delta, generated by the checkpoint node",
    )
    checkpoint_verified: bool = Field(
        default=False,
        description="True once the user has confirmed the checkpoint delta",
    )

    # ── Contract stamp ────────────────────────────────────────────────────────
    contract_version: str = Field(
        default=CONTRACT_VERSION,
        description="Schema version; consumers refuse on major-version mismatch",
    )


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
