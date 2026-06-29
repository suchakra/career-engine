"""Atomic workflow node implementations — Phase 1 (WS-A).

Every node is a PURE function: (CareerEngineState) -> CareerEngineState.
No UI imports.  No direct Firestore calls.  No hardcoded model names.
Model access goes through models.registry.get_registry().get_model_id().

On capability shortfall, nodes return UpgradeRequired (typed); they never raise.

Dependency injection:
    Model client access is abstracted through _get_model_client(), which can be
    replaced in tests via set_model_client_factory().  This keeps the nodes
    unit-testable without a live API key.

StarStory immutability:
    StarStory is frozen=True (config).  Nodes create NEW instances rather than
    mutating existing ones, using model_copy() or direct construction.

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

from config import get_settings
from models.registry import get_registry
from schema import (
    Capability,
    CareerEngineState,
    PhaseStatus,
    StarStory,
    UpgradeRequired,
)
from workflows.prompts import (
    CHECKPOINT_SUMMARY_PROMPT,
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


def _default_client_factory() -> ModelClient:
    """Return the default genai-backed model client."""
    import google.genai as genai

    settings = get_settings()
    api_key = settings.gemini_api_key or settings.dev_gemini_key or None

    class _GenaiClient:
        """Thin wrapper around google.genai for generate() calls."""

        def __init__(self, key: str | None) -> None:
            """Initialise with optional API key."""
            self._client = genai.Client(api_key=key) if key else genai.Client()

        def generate(self, model_id: str, system: str, user: str) -> str:
            """Call generate_content and return the text response."""
            from google.genai import types as gtypes

            response = self._client.models.generate_content(
                model=model_id,
                contents=user,
                config=gtypes.GenerateContentConfig(system_instruction=system),
            )
            return response.text or ""

    return _GenaiClient(api_key)


_client_factory: Callable[[], ModelClient] = _default_client_factory


def set_model_client_factory(factory: Callable[[], ModelClient]) -> None:
    """Replace the model client factory (for testing).

    Call this before the node functions are invoked to inject a mock client
    that does not make live API calls.
    """
    global _client_factory
    _client_factory = factory


def _get_model_client() -> ModelClient:
    """Return the current model client (real or injected mock)."""
    return _client_factory()


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
    """
    if not result_text:
        return False
    # Look for numeric patterns indicating a metric
    patterns = [
        r"\d+\s*ms\b",  # latency (milliseconds)
        r"\d+\s*s\b",  # seconds
        r"\d+\s*%",  # percentages
        r"\$\s*\d+",  # dollar amounts
        r"\d+\s*[kKmMbB]\b",  # k/M/B scale suffixes
        r"\d+\s+(?:services?|servers?|nodes?|instances?|engineers?|customers?|users?|requests?)",
        r"\bfrom\s+\d",  # before/after pattern ("from 800ms...")
        r"\d+\s*(?:minutes?|hours?|days?)",  # time durations
        r"\d+x\b",  # multiplier (2x, 10x)
        r"\d+\.\d+",  # decimal numbers
    ]
    for pattern in patterns:
        if re.search(pattern, result_text, re.IGNORECASE):
            return True
    return False


# ── Node implementations ──────────────────────────────────────────────────────


def ingest_node(state: CareerEngineState) -> CareerEngineState:
    """Parse raw career history and seed competency pillars and active gaps.

    Uses SPEED_FAST capability (Flash baseline).  Sends the raw history text
    to the model with INGEST_SYSTEM_PROMPT to extract competency pillars and
    the first pillar to explore.  Sets current_phase to GRILLING.

    Args:
        state: Input state with raw_history_text populated.

    Returns:
        Updated state with target_competencies, active_gaps, current_pillar,
        and current_phase=GRILLING.
    """
    model_id = _resolve_model(Capability.SPEED_FAST)
    if isinstance(model_id, UpgradeRequired):
        # SPEED_FAST is always resolvable in both modes; guard defensively.
        # Return state unchanged so the graph can route appropriately.
        return state

    client = _get_model_client()
    raw = state.raw_history_text.strip() or "(no career history provided)"
    response_text = client.generate(
        model_id=model_id,
        system=INGEST_SYSTEM_PROMPT,
        user=raw,
    )
    parsed = _parse_json_response(response_text)

    pillars: list[str] = parsed.get("competency_pillars", [])
    gaps: list[str] = parsed.get("initial_gaps", pillars[:])
    first_pillar: str = parsed.get("suggested_first_pillar", pillars[0] if pillars else "")

    # Fallback if model returned nothing useful
    if not pillars:
        pillars = ["general"]
        gaps = ["general"]
        first_pillar = "general"

    return state.model_copy(
        update={
            "current_phase": PhaseStatus.GRILLING,
            "target_competencies": pillars,
            "active_gaps": gaps,
            "current_pillar": first_pillar,
            "question_count": 0,
        }
    )


def execute_grill_turn_node(
    state: CareerEngineState,
) -> CareerEngineState | UpgradeRequired:
    """Ask one probing question and validate the user's answer for concrete metrics.

    Uses REASONING_HIGH capability with a Chain-of-Thought system prompt:
    decompose claim → demand a metric → plausibility-check → restate as STAR.
    Tone: senior peer over coffee; NEVER says "STAR" to the user.

    Two-step process per call (contract v1.1.0 — dedicated fields):
    1. If `pending_user_answer` is non-empty, run METRIC_EXTRACTION_PROMPT to
       parse it.  If metrics_found=True, create a StarStory
       (metrics_validated=True), remove the pillar from active_gaps, and clear
       `pending_user_answer`.  If metrics_found=False, set `current_question`
       to a follow-up metric question and clear `pending_user_answer`.
    2. If there is no pending answer (first question for a pillar), generate an
       opening question with GRILL_SYSTEM_PROMPT and set `current_question`.

    The user-facing question is ALWAYS surfaced via `current_question`; the
    user's answer is ALWAYS read from `pending_user_answer`.  No field is
    overloaded.

    Returns UpgradeRequired (typed) if REASONING_HIGH resolution fails in Free Mode
    after multiple Flash+CoT attempts — never raises.

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
    client = _get_model_client()

    # The dedicated `pending_user_answer` field (contract v1.1.0) carries the
    # user's most recent answer awaiting extraction.  When it is non-empty we
    # run metric extraction; otherwise we generate an opening question.
    user_answer = state.pending_user_answer.strip()

    new_question_count = state.question_count + 1

    if user_answer:
        # ── Step 1: try to extract a validated metric ─────────────────────
        extraction_context = (
            f"Competency pillar: {state.current_pillar}\n\n"
            f"User's answer:\n{user_answer}"
        )
        extraction_text = client.generate(
            model_id=model_id,
            system=METRIC_EXTRACTION_PROMPT,
            user=extraction_context,
        )
        extracted = _parse_json_response(extraction_text)
        metrics_found: bool = bool(extracted.get("metrics_found", False))
        result_text: str = extracted.get("result", "")

        # Double-check with our own regex (defensive layer)
        if metrics_found and not _contains_real_metric(result_text):
            metrics_found = False

        if metrics_found:
            # ── Commit a validated StarStory ──────────────────────────────
            story = StarStory(
                pillar=state.current_pillar,
                situation=extracted.get("situation", ""),
                task=extracted.get("task", ""),
                action=extracted.get("action", ""),
                result=result_text,
                metrics_validated=True,
            )
            new_stories = [*state.extracted_star_stories, story]
            # Remove this pillar from active_gaps
            new_gaps = [g for g in state.active_gaps if g != state.current_pillar]
            # Advance to next pillar if there are more gaps
            next_pillar = new_gaps[0] if new_gaps else state.current_pillar

            return state.model_copy(
                update={
                    "extracted_star_stories": new_stories,
                    "active_gaps": new_gaps,
                    "current_pillar": next_pillar,
                    "question_count": new_question_count,
                    # Answer processed: clear the pending buffer.  No new
                    # question this turn (the next grill turn opens the next
                    # pillar); current_question is cleared to avoid stale text.
                    "pending_user_answer": "",
                    "current_question": "",
                }
            )
        else:
            # ── Metrics not found: ask a probing follow-up question ────────
            probe_context = (
                f"Competency pillar: {state.current_pillar}\n\n"
                f"What the person said:\n{user_answer}\n\n"
                f"The answer lacked a concrete metric.  "
                f"Generate one sharp follow-up question to elicit a specific number."
            )
            question_text = client.generate(
                model_id=model_id,
                system=GRILL_SYSTEM_PROMPT,
                user=probe_context,
            )
            # Answer lacked a metric: surface the follow-up question via the
            # dedicated current_question field and clear the consumed answer.
            return state.model_copy(
                update={
                    "question_count": new_question_count,
                    "current_question": question_text.strip(),
                    "pending_user_answer": "",
                }
            )
    else:
        # ── Step 2: generate opening question for the current pillar ──────
        opening_context = (
            f"You are starting to explore the '{state.current_pillar}' pillar "
            f"with this person.  Ask them to describe a specific project or "
            f"situation where they demonstrated impact in this area.  "
            f"Keep it open and conversational — one question only."
        )
        question_text = client.generate(
            model_id=model_id,
            system=GRILL_SYSTEM_PROMPT,
            user=opening_context,
        )
        # Surface the opening question via the dedicated current_question field.
        return state.model_copy(
            update={
                "question_count": new_question_count,
                "current_question": question_text.strip(),
            }
        )


def user_checkpoint_node(state: CareerEngineState) -> CareerEngineState:
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
        summary = (
            f"So far we've captured {n} achievement(s).  "
            "Does everything sound accurate before we continue?"
        )
        return state.model_copy(
            update={
                "checkpoint_delta_summary": summary,
                "checkpoint_verified": False,
                "current_phase": PhaseStatus.CHECKPOINT,
            }
        )

    client = _get_model_client()

    # Summarise recent stories (last 5 or all if fewer)
    recent_stories = state.extracted_star_stories[-5:]
    stories_text = "\n\n".join(
        f"- {s.pillar}: {s.result}" if s.result else f"- {s.pillar}: (no metric yet)"
        for s in recent_stories
    )
    if not stories_text:
        stories_text = "(no achievements captured yet in this batch)"

    summary_input = (
        f"Recent achievements (last batch):\n{stories_text}\n\n"
        f"Total achievements captured so far: {len(state.extracted_star_stories)}\n"
        f"Remaining areas to explore: {', '.join(state.active_gaps) or 'none'}"
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


def finalize_master_resume_node(state: CareerEngineState) -> CareerEngineState:
    """Assemble all validated StarStories into the master resume structure.

    Uses SPEED_FAST capability (Flash baseline).  Sends the validated stories
    to FINALIZE_SYSTEM_PROMPT to produce a structured resume JSON.  Writes
    (contract v1.1.0 — dedicated fields):
      - `master_resume_json`: the structured resume JSON.
      - `professional_summary`: the prose summary (WS-B's pdf_renderer reads
        THIS to render the resume's summary section).
    Sets current_phase to COMPLETE.  Does NOT write checkpoint_delta_summary.

    Args:
        state: State with validated extracted_star_stories.

    Returns:
        State with current_phase=COMPLETE, master_resume_json populated, and
        professional_summary set to a prose summary.
    """
    model_id = _resolve_model(Capability.SPEED_FAST)
    if isinstance(model_id, UpgradeRequired):
        return state.model_copy(update={"current_phase": PhaseStatus.COMPLETE})

    client = _get_model_client()

    stories_payload = [
        {
            "pillar": s.pillar,
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


def tailor_node(state: CareerEngineState) -> CareerEngineState:
    """Produce a targeted resume variant from a cleaned job description.

    Uses SPEED_FAST capability (Flash baseline).  Reads (contract v1.1.0 —
    dedicated fields):
      - the cleaned JD from `jd_text`,
      - the master resume from `master_resume_json`.
    Writes the result to `tailored_resume_json`.  Leaves raw_history_text
    untouched (it now means raw career history only) and does NOT write
    checkpoint_delta_summary.

    Args:
        state: State with current_phase=COMPLETE, master_resume_json populated,
               and jd_text set to the cleaned job description.

    Returns:
        State with tailored_resume_json populated.
    """
    model_id = _resolve_model(Capability.SPEED_FAST)
    if isinstance(model_id, UpgradeRequired):
        return state

    client = _get_model_client()

    master_resume = state.master_resume_json
    jd_text = state.jd_text.strip() or "(no job description provided)"

    tailor_input = (
        f"MASTER RESUME:\n{master_resume}\n\n"
        f"JOB DESCRIPTION (cleaned):\n{jd_text}"
    )

    tailored_text = client.generate(
        model_id=model_id,
        system=TAILOR_SYSTEM_PROMPT,
        user=tailor_input,
    )

    return state.model_copy(
        update={
            "tailored_resume_json": tailored_text.strip(),
        }
    )
