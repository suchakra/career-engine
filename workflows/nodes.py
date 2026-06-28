"""Atomic workflow node function stubs — Phase 0 interface definitions.

Phase 0 — typed signatures only.  Phase 1 (WS-A) implements the node bodies.

Every node is a pure function: (CareerEngineState) -> CareerEngineState.
- No UI imports.
- No direct Firestore calls.
- No hardcoded model names — model access goes through models.registry.
- On capability shortfall, return UpgradeRequired (never raise).

ADK 2.0 wiring:
    Each function here is wrapped in a FunctionNode by discovery_graph.py.
    The FunctionNode's parameter_binding='state' means ADK reads/writes the
    named parameters to/from ctx.state automatically.  Since CareerEngineState
    is our contract object, it is extracted from state and passed in as the
    `state` parameter, then written back on return.

    Concrete Phase 1 nodes will be wrapped as:
        FunctionNode(func=ingest_node, name="ingest", state_schema=CareerEngineState)
"""

from __future__ import annotations

from schema import CareerEngineState, UpgradeRequired


def ingest_node(state: CareerEngineState) -> CareerEngineState:
    """Parse raw career history and seed pillars and active gaps.

    Uses SPEED_FAST capability (Flash baseline).  Sets current_phase to GRILLING
    and populates target_competencies and active_gaps.

    Args:
        state: Input state with raw_history_text populated.

    Returns:
        Updated state with target_competencies, active_gaps, and phase=GRILLING.
    """
    raise NotImplementedError("ingest_node is a Phase 1 task.")


def execute_grill_turn_node(
    state: CareerEngineState,
) -> CareerEngineState | UpgradeRequired:
    """Ask one probing question and validate the user's answer for concrete metrics.

    Uses REASONING_HIGH capability with a Chain-of-Thought system prompt:
    decompose claim → demand a metric → plausibility-check → restate as STAR.
    Tone: senior peer over coffee; never names "STAR" to the user.

    Returns UpgradeRequired (typed) if REASONING_HIGH is unavailable in Free Mode.
    Increments question_count on success; appends a StarStory when an answer
    contains validated metrics.

    Args:
        state: Current session state.

    Returns:
        Updated CareerEngineState or UpgradeRequired signal.
    """
    raise NotImplementedError("execute_grill_turn_node is a Phase 1 task.")


def user_checkpoint_node(state: CareerEngineState) -> CareerEngineState:
    """Hydration Point — summarise the last 5-turn delta and await user verification.

    Does NOT commit the delta until checkpoint_verified=True.
    Sets checkpoint_delta_summary; Phase 1 loops until the user confirms.

    Args:
        state: Current session state.

    Returns:
        State with checkpoint_delta_summary populated and checkpoint_verified=False
        (ready for user confirmation).
    """
    raise NotImplementedError("user_checkpoint_node is a Phase 1 task.")


def finalize_master_resume_node(state: CareerEngineState) -> CareerEngineState:
    """Assemble all validated StarStories into the master resume structure.

    Sets current_phase to COMPLETE.  Uses SPEED_FAST capability.

    Args:
        state: State with validated extracted_star_stories.

    Returns:
        State with current_phase=COMPLETE and a finalised resume structure.
    """
    raise NotImplementedError("finalize_master_resume_node is a Phase 1 task.")


def tailor_node(state: CareerEngineState) -> CareerEngineState:
    """Produce a targeted resume variant from a cleaned job description.

    Uses SPEED_FAST capability (Flash baseline).  Expects a cleaned JD to be
    present in state (mechanism to inject it defined in Phase 1).

    Args:
        state: State with a finalized master resume and a target JD.

    Returns:
        State with a tailored resume variant attached.
    """
    raise NotImplementedError("tailor_node is a Phase 1 task.")
