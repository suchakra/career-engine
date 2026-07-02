"""Tests for the Phase 3 vague-applicant evaluation harness.

Drives the REAL discovery graph deterministically (scripted agent + fixture
applicant). Verifies: vague answers are pushed back and a specific one yields a
validated metric-bearing StarStory; the 5-turn checkpoint brake fires; and the
Pro-escalation rate is recorded (0 on the happy path, >0 when REASONING_HIGH is
refused).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from config import AccessMode
from evaluation.user_simulator import (
    Scenario,
    load_scenarios,
    run_simulation,
)
from models.registry import BaseModelRegistry, DefaultModelRegistry, get_registry, set_registry
from schema import Capability, UpgradeRequired
from workflows.nodes import _contains_real_metric

_CONFIG = Path(__file__).resolve().parent.parent / "evaluation" / "test_config.json"


def _scenario(name: str) -> Scenario:
    return next(s for s in load_scenarios(_CONFIG) if s.name == name)


@pytest.fixture(autouse=True)
def _restore_registry() -> object:
    """Restore the global registry after tests that swap it."""
    original = get_registry()
    yield None
    set_registry(original)


class TestConfigLoads:
    """The bundled scenarios load from test_config.json."""

    def test_loads_two_scenarios(self) -> None:
        names = {s.name for s in load_scenarios(_CONFIG)}
        assert {"eventually_specific", "persistent_vague"} <= names


class TestGrillPushback:
    """A vague answer is rejected; a specific one yields a validated metric story."""

    def test_eventually_specific_yields_validated_metric_story(self) -> None:
        result = run_simulation(_scenario("eventually_specific"))
        assert len(result.validated_stories) >= 1
        story = result.validated_stories[0]
        assert story.metrics_validated is True
        assert _contains_real_metric(story.result), "validated story must carry a real metric"

    def test_transcript_records_a_vague_then_specific_progression(self) -> None:
        result = run_simulation(_scenario("eventually_specific"))
        # At least one vague answer was given before the metric-bearing one.
        answers = [t.answer for t in result.transcript]
        assert any(not _contains_real_metric(a) for a in answers)
        assert any(_contains_real_metric(a) for a in answers)


class TestCheckpointBrake:
    """The 5-turn checkpoint brake fires for a persistently-vague applicant."""

    def test_checkpoint_fires_at_question_count_5(self) -> None:
        result = run_simulation(_scenario("persistent_vague"))
        assert result.checkpoint_fired is True
        assert result.checkpoint_question_count == 5

    def test_persistent_vague_escalates_after_checkpoint_and_validates_nothing(self) -> None:
        """A never-specific applicant hits the checkpoint, then the Pro-escalation gate.

        The 5-turn checkpoint brake fires first (qc=5); a user who stays vague on
        the same entry past it trips the Free-Mode escalation gate rather than
        looping forever. No story is validated, and it is a clean escalation (not
        a max_turns truncation).
        """
        result = run_simulation(_scenario("persistent_vague"))
        assert result.checkpoint_question_count == 5
        assert result.escalations >= 1
        assert result.pro_escalation_rate > 0.0
        assert result.truncated is False
        assert result.validated_stories == []


class TestProEscalationRate:
    """The Pro-escalation rate is recorded — 0 on happy path, >0 when reasoning refused."""

    def test_rate_zero_on_happy_path(self) -> None:
        result = run_simulation(_scenario("eventually_specific"))
        assert result.pro_escalation_rate == 0.0
        assert result.escalations == 0

    def test_rate_positive_when_reasoning_high_refused(self) -> None:
        class _NoReasoningRegistry(BaseModelRegistry):
            def get_model_id(
                self, capability: Capability, *, access_mode: AccessMode | None = None
            ) -> str | UpgradeRequired:
                if capability == Capability.REASONING_HIGH:
                    return UpgradeRequired(
                        required_capability=capability,
                        node_name="_NoReasoningRegistry",
                        reason="no reasoning model in free tier",
                    )
                return DefaultModelRegistry().get_model_id(capability, access_mode=access_mode)

            def supports(self, capability: Capability, *, access_mode: AccessMode) -> bool:
                return capability != Capability.REASONING_HIGH

        set_registry(_NoReasoningRegistry())
        result = run_simulation(_scenario("eventually_specific"))
        assert result.escalations >= 1
        assert result.pro_escalation_rate > 0.0


class TestDeterminism:
    """Repeated runs are identical (no live-model variance)."""

    def test_repeated_runs_match(self) -> None:
        r1 = run_simulation(_scenario("eventually_specific"))
        r2 = run_simulation(_scenario("eventually_specific"))
        # Eval-relevant outputs are identical across runs. (StarStory.story_id /
        # extracted_at are incidental schema nondeterminism and are excluded.)
        assert len(r1.validated_stories) == len(r2.validated_stories)
        assert [t.answer for t in r1.transcript] == [t.answer for t in r2.transcript]
        assert [t.question for t in r1.transcript] == [t.question for t in r2.transcript]
        assert [s.result for s in r1.validated_stories] == [s.result for s in r2.validated_stories]
        assert r1.checkpoint_question_count == r2.checkpoint_question_count
        assert r1.grill_turns == r2.grill_turns
        assert r1.pro_escalation_rate == r2.pro_escalation_rate
