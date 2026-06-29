"""Unit tests for the pure workflow node functions (WS-A).

All model calls are mocked via set_model_client_factory — no live API calls.
Every test is deterministic.

Acceptance criteria covered (see docs/AGENT_EXECUTION_PROMPT.md WS-A block):
- vague answer is REJECTED (asks for a metric; no validated StarStory committed)
- specific answer yields a StarStory with result populated + metrics_validated=True
- checkpoint node does NOT commit/advance until checkpoint_verified is True
- REASONING_HIGH shortfall in FREE mode -> UpgradeRequired (typed), never raises
- each node is pure: same input -> same output, deps mocked, no external mutation
"""

from __future__ import annotations

import json

import pytest

from config import AccessMode
from models.registry import (
    BaseModelRegistry,
    DefaultModelRegistry,
    get_registry,
    set_registry,
)
from schema import (
    Capability,
    CareerEngineState,
    PhaseStatus,
    StarStory,
    UpgradeRequired,
)
from workflows import nodes
from workflows.nodes import (
    _contains_real_metric,
    execute_grill_turn_node,
    finalize_master_resume_node,
    ingest_node,
    set_model_client_factory,
    tailor_node,
    user_checkpoint_node,
)

# ── Test doubles ──────────────────────────────────────────────────────────────


class ScriptedClient:
    """A model client that returns scripted responses keyed by system prompt prefix.

    Records every call so tests can assert which prompts were used.  Never makes
    a network call.
    """

    def __init__(self, responses: dict[str, str] | None = None, default: str = "") -> None:
        """Initialise with a {system-prompt-substring: response} map."""
        self._responses = responses or {}
        self._default = default
        self.calls: list[dict[str, str]] = []

    def generate(self, model_id: str, system: str, user: str) -> str:
        """Return a scripted response, matching on a substring of the system prompt."""
        self.calls.append({"model_id": model_id, "system": system, "user": user})
        for key, resp in self._responses.items():
            if key in system:
                return resp
        return self._default


def _install_client(client: ScriptedClient) -> None:
    """Install a scripted client as the node model-client factory."""
    set_model_client_factory(lambda: client)


@pytest.fixture(autouse=True)
def _reset_registry_and_client() -> object:
    """Restore the registry and client factory after each test."""
    original_registry = get_registry()
    yield None
    set_registry(original_registry)
    nodes.set_model_client_factory(nodes._default_client_factory)


@pytest.fixture(autouse=True)
def _force_free_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force FREE access mode for deterministic registry resolution."""
    from config import Settings

    def _free_settings() -> Settings:
        return Settings(access_mode=AccessMode.FREE)

    monkeypatch.setattr(nodes, "get_settings", _free_settings)


# ── _contains_real_metric ─────────────────────────────────────────────────────


class TestContainsRealMetric:
    """The metric-detection helper distinguishes real metrics from vague claims."""

    def test_vague_text_has_no_metric(self) -> None:
        """Vague qualifiers do not count as a metric."""
        assert _contains_real_metric("I improved performance a lot") is False
        assert _contains_real_metric("significantly better than before") is False
        assert _contains_real_metric("") is False

    def test_latency_metric_detected(self) -> None:
        """A before/after latency figure counts as a metric."""
        assert _contains_real_metric("cut p99 from 800ms to 120ms across 40 services") is True

    def test_percentage_metric_detected(self) -> None:
        """A percentage figure counts as a metric."""
        assert _contains_real_metric("reduced error rate by 85%") is True

    def test_scale_metric_detected(self) -> None:
        """A scale figure counts as a metric."""
        assert _contains_real_metric("served 2M requests per day") is True

    def test_dollar_metric_detected(self) -> None:
        """A dollar figure counts as a metric."""
        assert _contains_real_metric("saved $50k per month") is True


# ── execute_grill_turn_node — vague answer rejected ───────────────────────────


class TestGrillVagueAnswerRejected:
    """A vague answer must be REJECTED: a follow-up is asked, no story committed."""

    def test_vague_answer_does_not_commit_story(self) -> None:
        """'I improved performance a lot' -> no validated StarStory; metric demanded."""
        client = ScriptedClient(
            responses={
                # Extraction prompt: model reports no metric found
                "data extraction assistant": json.dumps(
                    {
                        "situation": "perf work",
                        "task": "make it faster",
                        "action": "tuned things",
                        "result": "improved performance a lot",
                        "metrics_found": False,
                        "metric_summary": "",
                    }
                ),
                # Grill prompt: model asks a follow-up demanding a number
                "senior engineering colleague": (
                    "What did the latency look like before and after, roughly?"
                ),
            }
        )
        _install_client(client)

        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            current_pillar="performance_engineering",
            active_gaps=["performance_engineering"],
            pending_user_answer="I improved performance a lot",
        )
        result = execute_grill_turn_node(state)

        assert isinstance(result, CareerEngineState)
        # No story committed
        assert result.extracted_star_stories == []
        # Pillar still in gaps (not resolved)
        assert "performance_engineering" in result.active_gaps
        # A follow-up question is surfaced via the dedicated current_question field
        assert result.current_question != ""
        assert "latency" in result.current_question.lower()
        # The consumed answer is cleared
        assert result.pending_user_answer == ""
        # checkpoint_delta_summary is NOT overloaded by the grill node
        assert result.checkpoint_delta_summary == ""
        # question_count incremented
        assert result.question_count == 1

    def test_extraction_claims_metric_but_text_is_vague_still_rejected(self) -> None:
        """Defense-in-depth: model says metrics_found=True but result has no number."""
        client = ScriptedClient(
            responses={
                "data extraction assistant": json.dumps(
                    {
                        "situation": "s",
                        "task": "t",
                        "action": "a",
                        "result": "made it much faster overall",
                        "metrics_found": True,  # model lies
                        "metric_summary": "faster",
                    }
                ),
                "senior engineering colleague": "How much faster, in concrete numbers?",
            }
        )
        _install_client(client)

        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            current_pillar="delivery",
            active_gaps=["delivery"],
            pending_user_answer="made it much faster overall",
        )
        result = execute_grill_turn_node(state)

        assert isinstance(result, CareerEngineState)
        # The regex gate overrides the model's false claim -> no story
        assert result.extracted_star_stories == []
        assert "delivery" in result.active_gaps
        # Answer consumed; a follow-up question surfaced
        assert result.pending_user_answer == ""
        assert result.current_question != ""


# ── execute_grill_turn_node — specific answer accepted ────────────────────────


class TestGrillSpecificAnswerAccepted:
    """A specific, metric-rich answer must produce a validated StarStory."""

    def test_specific_answer_yields_validated_story(self) -> None:
        """'cut p99 from 800ms to 120ms across 40 services' -> validated StarStory."""
        answer = "cut p99 from 800ms to 120ms across 40 services"
        client = ScriptedClient(
            responses={
                "data extraction assistant": json.dumps(
                    {
                        "situation": "High p99 latency under peak load.",
                        "task": "Reduce tail latency across the fleet.",
                        "action": "Added caching and removed N+1 queries.",
                        "result": answer,
                        "metrics_found": True,
                        "metric_summary": "p99 800->120ms across 40 services",
                    }
                ),
            }
        )
        _install_client(client)

        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            current_pillar="performance_engineering",
            active_gaps=["performance_engineering"],
            pending_user_answer=answer,
        )
        result = execute_grill_turn_node(state)

        assert isinstance(result, CareerEngineState)
        assert len(result.extracted_star_stories) == 1
        story = result.extracted_star_stories[0]
        assert isinstance(story, StarStory)
        assert story.result == answer
        assert story.metrics_validated is True
        assert story.pillar == "performance_engineering"
        # Pillar removed from active_gaps once a validated story exists
        assert "performance_engineering" not in result.active_gaps
        # The committed answer is cleared from the pending buffer
        assert result.pending_user_answer == ""
        # No overloading: raw_history_text (raw career history) is untouched and
        # checkpoint_delta_summary is not used by the grill node
        assert result.raw_history_text == ""
        assert result.checkpoint_delta_summary == ""

    def test_opening_question_when_no_pending_answer(self) -> None:
        """With no pending answer, the node generates an opening question."""
        client = ScriptedClient(
            responses={
                "senior engineering colleague": (
                    "Tell me about a project where you drove real impact here."
                )
            }
        )
        _install_client(client)

        # Empty pending_user_answer means there is no answer to extract;
        # the node generates an opening question instead.
        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            current_pillar="leadership",
            active_gaps=["leadership"],
            pending_user_answer="",
        )
        result = execute_grill_turn_node(state)

        assert isinstance(result, CareerEngineState)
        assert result.extracted_star_stories == []
        # Opening question surfaced via the dedicated current_question field
        assert result.current_question != ""
        assert result.checkpoint_delta_summary == ""
        assert result.question_count == 1


# ── execute_grill_turn_node — never says "STAR" ───────────────────────────────


class TestGrillNeverSaysStar:
    """The grill prompt must never expose the internal STAR framework to the user."""

    def test_grill_system_prompt_warns_against_star(self) -> None:
        """The CoT system prompt explicitly forbids naming STAR to the user."""
        from workflows.prompts import GRILL_SYSTEM_PROMPT

        assert "STAR" in GRILL_SYSTEM_PROMPT  # it is mentioned as a forbidden term
        assert "Never use the word" in GRILL_SYSTEM_PROMPT


# ── execute_grill_turn_node — UpgradeRequired on REASONING_HIGH shortfall ──────


class _NoReasoningRegistry(BaseModelRegistry):
    """A registry that refuses REASONING_HIGH to simulate a Free-mode shortfall."""

    def get_model_id(
        self,
        capability: Capability,
        *,
        access_mode: AccessMode | None = None,
    ) -> str | UpgradeRequired:
        """Return UpgradeRequired for REASONING_HIGH; resolve others normally."""
        if capability == Capability.REASONING_HIGH:
            return UpgradeRequired(
                required_capability=capability,
                node_name="_NoReasoningRegistry",
                reason="No reasoning-capable free model available.",
            )
        return DefaultModelRegistry().get_model_id(capability, access_mode=access_mode)

    def supports(self, capability: Capability, *, access_mode: AccessMode) -> bool:
        """REASONING_HIGH unsupported; others supported."""
        return capability != Capability.REASONING_HIGH


class TestGrillUpgradeRequired:
    """A REASONING_HIGH shortfall returns UpgradeRequired (typed), never raises."""

    def test_reasoning_shortfall_returns_upgrade_required(self) -> None:
        """When the registry refuses REASONING_HIGH, the node returns UpgradeRequired."""
        set_registry(_NoReasoningRegistry())
        _install_client(ScriptedClient(default="{}"))

        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            current_pillar="scale",
            active_gaps=["scale"],
            pending_user_answer="some answer",
        )
        result = execute_grill_turn_node(state)

        assert isinstance(result, UpgradeRequired)
        assert result.required_capability == Capability.REASONING_HIGH

    def test_reasoning_shortfall_does_not_raise(self) -> None:
        """The shortfall path must not raise any exception."""
        set_registry(_NoReasoningRegistry())
        _install_client(ScriptedClient(default="{}"))

        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            current_pillar="scale",
            active_gaps=["scale"],
            pending_user_answer="x",
        )
        # Should simply return, never raise
        result = execute_grill_turn_node(state)
        assert isinstance(result, UpgradeRequired)


# ── user_checkpoint_node — does not commit until verified ─────────────────────


class TestCheckpointNode:
    """The checkpoint (Hydration Point) must not advance until verified."""

    def test_checkpoint_summarizes_and_waits(self) -> None:
        """Unverified entry -> summary produced, phase=CHECKPOINT, NOT advanced."""
        client = ScriptedClient(
            responses={
                "summarizing progress": (
                    "You described cutting p99 latency 85%. Does that sound right?"
                )
            }
        )
        _install_client(client)

        story = StarStory(
            pillar="performance_engineering",
            result="cut p99 from 800ms to 120ms",
            metrics_validated=True,
        )
        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            extracted_star_stories=[story],
            active_gaps=["leadership"],
            checkpoint_verified=False,
        )
        result = user_checkpoint_node(state)

        assert isinstance(result, CareerEngineState)
        # Summary produced
        assert result.checkpoint_delta_summary != ""
        # Did NOT advance — still awaiting verification
        assert result.checkpoint_verified is False
        assert result.current_phase == PhaseStatus.CHECKPOINT

    def test_checkpoint_advances_only_when_verified(self) -> None:
        """Verified entry -> phase advances back to GRILLING and flag resets."""
        _install_client(ScriptedClient(default="summary"))

        state = CareerEngineState(
            current_phase=PhaseStatus.CHECKPOINT,
            checkpoint_verified=True,
            checkpoint_delta_summary="some prior summary",
            active_gaps=["leadership"],
        )
        result = user_checkpoint_node(state)

        assert result.current_phase == PhaseStatus.GRILLING
        assert result.checkpoint_verified is False
        assert result.checkpoint_delta_summary == ""


# ── ingest_node ───────────────────────────────────────────────────────────────


class TestIngestNode:
    """Ingest seeds pillars/gaps and moves the session into the grill phase."""

    def test_ingest_seeds_pillars_and_gaps(self) -> None:
        """Ingest parses history into competency pillars and active gaps."""
        client = ScriptedClient(
            responses={
                "key competency areas": json.dumps(
                    {
                        "competency_pillars": ["leadership", "delivery", "scale"],
                        "initial_gaps": ["leadership", "delivery", "scale"],
                        "suggested_first_pillar": "delivery",
                        "summary": "Senior engineer.",
                    }
                )
            }
        )
        _install_client(client)

        state = CareerEngineState(raw_history_text="20 years building distributed systems.")
        result = ingest_node(state)

        assert result.current_phase == PhaseStatus.GRILLING
        assert result.target_competencies == ["leadership", "delivery", "scale"]
        assert result.active_gaps == ["leadership", "delivery", "scale"]
        assert result.current_pillar == "delivery"

    def test_ingest_fallback_when_model_returns_nothing(self) -> None:
        """If the model returns no pillars, a 'general' fallback is seeded."""
        _install_client(ScriptedClient(default="not json at all"))

        state = CareerEngineState(raw_history_text="some history")
        result = ingest_node(state)

        assert result.current_phase == PhaseStatus.GRILLING
        assert result.active_gaps == ["general"]
        assert result.current_pillar == "general"


# ── finalize_master_resume_node ───────────────────────────────────────────────


class TestFinalizeNode:
    """Finalize assembles validated stories and marks the session COMPLETE."""

    def test_finalize_sets_master_resume_and_summary(self) -> None:
        """Finalize sets phase=COMPLETE, master_resume_json, and professional_summary."""
        client = ScriptedClient(
            responses={
                "assembling a master resume": json.dumps(
                    {"summary": "Impactful engineer.", "achievements_by_pillar": {}}
                )
            }
        )
        _install_client(client)

        story = StarStory(
            pillar="delivery",
            result="cut deploy time from 45min to 3min",
            metrics_validated=True,
        )
        state = CareerEngineState(
            current_phase=PhaseStatus.FINALIZING,
            extracted_star_stories=[story],
        )
        result = finalize_master_resume_node(state)

        assert result.current_phase == PhaseStatus.COMPLETE
        # Structured resume written to its dedicated field
        assert result.master_resume_json != ""
        assert "achievements_by_pillar" in result.master_resume_json
        # Prose summary extracted for the PDF renderer (WS-B reads THIS)
        assert result.professional_summary == "Impactful engineer."
        # checkpoint_delta_summary is NOT overloaded by finalize
        assert result.checkpoint_delta_summary == ""


# ── tailor_node ───────────────────────────────────────────────────────────────


class TestTailorNode:
    """Tailor produces a JD-targeted variant in its dedicated field."""

    def test_tailor_reads_jd_and_master_writes_tailored(self) -> None:
        """Tailor reads jd_text + master_resume_json and writes tailored_resume_json."""
        tailored = json.dumps(
            {"tailored_summary": "Great fit.", "selected_achievements": []}
        )
        client = ScriptedClient(
            responses={"tailoring a master resume": tailored}
        )
        _install_client(client)

        state = CareerEngineState(
            current_phase=PhaseStatus.COMPLETE,
            master_resume_json='{"summary": "master"}',
            jd_text="We need a backend engineer with Go and Kubernetes.",
        )
        result = tailor_node(state)

        # Result written to its dedicated field
        assert result.tailored_resume_json == tailored
        # raw_history_text and checkpoint_delta_summary are untouched
        assert result.raw_history_text == ""
        assert result.checkpoint_delta_summary == ""

    def test_tailor_uses_jd_and_master_in_model_call(self) -> None:
        """The tailor node feeds jd_text and master_resume_json into the model."""
        client = ScriptedClient(
            responses={"tailoring a master resume": "{}"}
        )
        _install_client(client)

        state = CareerEngineState(
            current_phase=PhaseStatus.COMPLETE,
            master_resume_json="MASTER_MARKER",
            jd_text="JD_MARKER",
        )
        tailor_node(state)

        assert client.calls, "tailor never called the model"
        prompt = client.calls[-1]["user"]
        assert "MASTER_MARKER" in prompt
        assert "JD_MARKER" in prompt


# ── Purity — same input -> same output, no external mutation ──────────────────


class TestNodePurity:
    """Each node is a pure function: deterministic and non-mutating of its input."""

    def _client_for_grill(self) -> ScriptedClient:
        return ScriptedClient(
            responses={
                "data extraction assistant": json.dumps(
                    {
                        "situation": "s",
                        "task": "t",
                        "action": "a",
                        "result": "cut p99 from 800ms to 120ms",
                        "metrics_found": True,
                        "metric_summary": "p99",
                    }
                )
            }
        )

    def test_grill_is_deterministic(self) -> None:
        """Same input through grill twice -> equal output."""
        _install_client(self._client_for_grill())
        base = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            current_pillar="perf",
            active_gaps=["perf"],
            pending_user_answer="cut p99 from 800ms to 120ms",
        )
        # Two independent input copies
        r1 = execute_grill_turn_node(base.model_copy(deep=True))
        r2 = execute_grill_turn_node(base.model_copy(deep=True))
        assert isinstance(r1, CareerEngineState)
        assert isinstance(r2, CareerEngineState)
        # Compare ignoring the auto-generated story_id/extracted_at timestamps
        s1 = r1.extracted_star_stories[0]
        s2 = r2.extracted_star_stories[0]
        assert s1.result == s2.result
        assert s1.metrics_validated == s2.metrics_validated
        assert r1.active_gaps == r2.active_gaps
        assert r1.question_count == r2.question_count

    def test_grill_does_not_mutate_input(self) -> None:
        """The input state object is not mutated by the node."""
        _install_client(self._client_for_grill())
        original = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            current_pillar="perf",
            active_gaps=["perf"],
            pending_user_answer="cut p99 from 800ms to 120ms",
            question_count=0,
        )
        snapshot = original.model_dump_json()
        _ = execute_grill_turn_node(original)
        # Input unchanged after the call
        assert original.model_dump_json() == snapshot
        assert original.extracted_star_stories == []
        assert original.question_count == 0

    def test_checkpoint_does_not_mutate_input(self) -> None:
        """The checkpoint node does not mutate its input state."""
        _install_client(ScriptedClient(default="summary text"))
        original = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            extracted_star_stories=[],
            active_gaps=["x"],
            checkpoint_verified=False,
        )
        snapshot = original.model_dump_json()
        _ = user_checkpoint_node(original)
        assert original.model_dump_json() == snapshot

    def test_ingest_does_not_mutate_input(self) -> None:
        """The ingest node does not mutate its input state."""
        _install_client(
            ScriptedClient(
                responses={
                    "key competency areas": json.dumps(
                        {
                            "competency_pillars": ["a"],
                            "initial_gaps": ["a"],
                            "suggested_first_pillar": "a",
                            "summary": "x",
                        }
                    )
                }
            )
        )
        original = CareerEngineState(raw_history_text="history")
        snapshot = original.model_dump_json()
        _ = ingest_node(original)
        assert original.model_dump_json() == snapshot


# ── No-hardcoded-model assertion (capabilities requested via registry) ────────


class TestNoHardcodedModels:
    """Nodes must request models by capability, resolved through the registry."""

    def test_grill_requests_reasoning_high_model(self) -> None:
        """The grill node calls the model with the REASONING_HIGH-resolved model id."""
        client = ScriptedClient(
            responses={
                "data extraction assistant": json.dumps(
                    {"result": "cut p99 from 800ms to 120ms", "metrics_found": True}
                )
            }
        )
        _install_client(client)

        registry = get_registry()
        expected_model: str | UpgradeRequired = registry.get_model_id(
            Capability.REASONING_HIGH, access_mode=AccessMode.FREE
        )

        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            current_pillar="perf",
            active_gaps=["perf"],
            pending_user_answer="cut p99 from 800ms to 120ms",
        )
        execute_grill_turn_node(state)

        assert isinstance(expected_model, str)
        assert client.calls, "model client was never called"
        assert all(c["model_id"] == expected_model for c in client.calls)
