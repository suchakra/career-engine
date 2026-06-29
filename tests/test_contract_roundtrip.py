"""Golden round-trip type tests for all Phase-0 Pydantic models.

Every model is serialised with model_dump_json() and deserialised with
model_validate_json(), then asserted equal to the original.  This proves
that the schema contract survives the JSON boundary without data loss or
silent coercion.

These tests are the Phase-0 CI gate.  `make test` must keep them green.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel

from config import CONTRACT_VERSION, AccessMode
from schema import (
    AgentMessage,
    Capability,
    CareerEngineState,
    PhaseStatus,
    StarStory,
    UpgradeRequired,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _roundtrip[M: BaseModel](model_instance: M) -> M:
    """Serialise and deserialise a Pydantic model; return the reconstructed instance."""
    cls = type(model_instance)
    json_str = model_instance.model_dump_json()
    return cls.model_validate_json(json_str)


# ── StarStory ─────────────────────────────────────────────────────────────────


class TestStarStoryRoundTrip:
    """Round-trip tests for StarStory."""

    def test_minimal_star_story(self) -> None:
        """A minimal StarStory (only required fields) survives round-trip."""
        original = StarStory(pillar="technical_leadership")
        reconstructed = _roundtrip(original)
        assert original == reconstructed

    def test_full_star_story(self) -> None:
        """A fully-populated StarStory survives round-trip."""
        original = StarStory(
            story_id=uuid4(),
            pillar="performance_engineering",
            situation="System was hitting 2000ms p99 latency under peak load.",
            task="Reduce p99 to under 200ms for the checkout service.",
            action="Profiled with async traces; identified N+1 queries; added Redis cache layer.",
            result="Cut p99 from 2000ms to 120ms across 40 services; 85% cache hit rate.",
            metrics_validated=True,
            extracted_at=datetime(2026, 6, 28, 12, 0, 0, tzinfo=UTC),
        )
        reconstructed = _roundtrip(original)
        assert original == reconstructed

    def test_metrics_validated_false_by_default(self) -> None:
        """metrics_validated defaults to False (no story is pre-validated)."""
        story = StarStory(pillar="impact")
        assert story.metrics_validated is False

    def test_star_story_json_contains_no_secrets(self) -> None:
        """StarStory JSON must not contain any secret-like field names."""
        story = StarStory(pillar="security")
        data = json.loads(story.model_dump_json())
        forbidden = {"api_key", "token", "password", "secret", "credential"}
        assert forbidden.isdisjoint(set(data.keys())), (
            f"StarStory JSON contains forbidden field(s): {forbidden & set(data.keys())}"
        )


# ── CareerEngineState ─────────────────────────────────────────────────────────


class TestCareerEngineStateRoundTrip:
    """Round-trip tests for CareerEngineState."""

    def test_default_state(self) -> None:
        """Default CareerEngineState (empty session) survives round-trip."""
        original = CareerEngineState()
        reconstructed = _roundtrip(original)
        assert original == reconstructed

    def test_state_with_stories(self) -> None:
        """State carrying StarStory objects survives round-trip."""
        story = StarStory(
            pillar="delivery",
            result="Reduced deploy time from 45 min to 3 min.",
            metrics_validated=True,
        )
        original = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            current_pillar="delivery",
            target_competencies=["delivery", "leadership", "scale"],
            active_gaps=["leadership", "scale"],
            extracted_star_stories=[story],
            question_count=3,
        )
        reconstructed = _roundtrip(original)
        assert original == reconstructed

    def test_state_carries_contract_version(self) -> None:
        """CareerEngineState must be stamped with CONTRACT_VERSION."""
        state = CareerEngineState()
        assert state.contract_version == CONTRACT_VERSION

    def test_state_has_no_user_id_field(self) -> None:
        """CareerEngineState must NOT carry user_id (travels via session/context)."""
        state = CareerEngineState()
        data = json.loads(state.model_dump_json())
        assert "user_id" not in data, "user_id must not appear in CareerEngineState JSON"

    def test_state_has_no_secret_fields(self) -> None:
        """CareerEngineState JSON must not contain any secret-like field names."""
        state = CareerEngineState()
        data = json.loads(state.model_dump_json())
        forbidden = {"api_key", "token", "password", "secret", "credential", "gemini_key"}
        assert forbidden.isdisjoint(set(data.keys())), (
            f"CareerEngineState JSON contains forbidden field(s): {forbidden & set(data.keys())}"
        )

    def test_state_phase_enum_roundtrip(self) -> None:
        """Phase enum values survive round-trip for all enum members."""
        for phase in PhaseStatus:
            original = CareerEngineState(current_phase=phase)
            reconstructed = _roundtrip(original)
            assert reconstructed.current_phase == phase

    def test_checkpoint_brake_fields(self) -> None:
        """Checkpoint-related fields default correctly and survive round-trip."""
        state = CareerEngineState(
            checkpoint_delta_summary="You described 3 achievements; 2 need metrics.",
            checkpoint_verified=False,
        )
        reconstructed = _roundtrip(state)
        assert reconstructed.checkpoint_delta_summary == state.checkpoint_delta_summary
        assert reconstructed.checkpoint_verified is False

    def test_v110_fields_default_and_roundtrip(self) -> None:
        """v1.1.0 fields default to empty and survive round-trip when populated."""
        default = CareerEngineState()
        assert default.pending_user_answer == ""
        assert default.current_question == ""
        assert default.professional_summary == ""
        assert default.master_resume_json == ""
        assert default.tailored_resume_json == ""
        assert default.jd_text == ""

        state = CareerEngineState(
            pending_user_answer="Cut p99 from 800ms to 120ms.",
            current_question="What was the scale?",
            professional_summary="Principal engineer with a record of latency wins.",
            master_resume_json='{"sections": []}',
            tailored_resume_json='{"tailored": true}',
            jd_text="Required: Python, distributed systems.",
        )
        reconstructed = _roundtrip(state)
        assert reconstructed == state


# ── AgentMessage ──────────────────────────────────────────────────────────────


class TestAgentMessageRoundTrip:
    """Round-trip tests for AgentMessage (inter-agent envelope)."""

    def test_basic_envelope(self) -> None:
        """A basic AgentMessage envelope survives round-trip."""
        original = AgentMessage(
            sender="ingest_node",
            recipient="execute_grill_turn_node",
            payload={"status": "ready"},
            payload_type="CareerEngineState",
        )
        reconstructed = _roundtrip(original)
        assert original == reconstructed

    def test_envelope_carries_contract_version(self) -> None:
        """AgentMessage must be stamped with CONTRACT_VERSION."""
        msg = AgentMessage(
            sender="a",
            recipient="b",
            payload={},
            payload_type="CareerEngineState",
        )
        assert msg.contract_version == CONTRACT_VERSION

    def test_envelope_with_state_payload(self) -> None:
        """An envelope carrying a serialised CareerEngineState payload survives round-trip."""
        state = CareerEngineState(question_count=5)
        original = AgentMessage(
            sender="grill_node",
            recipient="checkpoint_node",
            payload=json.loads(state.model_dump_json()),
            payload_type="schema.CareerEngineState",
        )
        reconstructed = _roundtrip(original)
        assert original == reconstructed
        # Reconstruct the inner payload
        inner = CareerEngineState.model_validate(reconstructed.payload)
        assert inner.question_count == 5


# ── UpgradeRequired ───────────────────────────────────────────────────────────


class TestUpgradeRequiredRoundTrip:
    """Round-trip tests for UpgradeRequired signal."""

    def test_upgrade_required_roundtrip(self) -> None:
        """UpgradeRequired signal survives round-trip."""
        original = UpgradeRequired(
            required_capability=Capability.REASONING_HIGH,
            node_name="execute_grill_turn_node",
            reason="REASONING_HIGH not available in Free Mode.",
        )
        reconstructed = _roundtrip(original)
        assert original == reconstructed

    def test_upgrade_required_carries_contract_version(self) -> None:
        """UpgradeRequired must be stamped with CONTRACT_VERSION."""
        signal = UpgradeRequired(
            required_capability=Capability.REASONING_HIGH,
            node_name="test_node",
            reason="test",
        )
        assert signal.contract_version == CONTRACT_VERSION

    def test_upgrade_required_default_user_message(self) -> None:
        """UpgradeRequired carries a default, ready-to-display user message."""
        signal = UpgradeRequired(
            required_capability=Capability.REASONING_HIGH,
            node_name="grill",
            reason="no free model",
        )
        msg_lower = signal.user_message.lower()
        assert "api key" in msg_lower or "upgrade" in msg_lower

    def test_all_capability_variants(self) -> None:
        """All Capability enum values can appear in UpgradeRequired and round-trip."""
        for cap in Capability:
            original = UpgradeRequired(
                required_capability=cap,
                node_name="test",
                reason=f"test for {cap.value}",
            )
            reconstructed = _roundtrip(original)
            assert reconstructed.required_capability == cap


# ── Capability enum ───────────────────────────────────────────────────────────


class TestCapabilityEnum:
    """Tests for the Capability enum."""

    def test_all_members_present(self) -> None:
        """All three required capability values must be present."""
        values = {c.value for c in Capability}
        assert "reasoning_high" in values
        assert "speed_fast" in values
        assert "bulk_cheap" in values

    def test_capability_is_str_enum(self) -> None:
        """Capability must be a str enum (serialisable as a plain string)."""
        assert isinstance(Capability.REASONING_HIGH, str)
        # StrEnum: the value IS the string
        assert str(Capability.REASONING_HIGH) == "reasoning_high"


# ── Contract version ──────────────────────────────────────────────────────────


class TestContractVersion:
    """Tests to ensure CONTRACT_VERSION is semver-formatted and consistent."""

    def test_contract_version_is_semver(self) -> None:
        """CONTRACT_VERSION must be a valid semver string (MAJOR.MINOR.PATCH)."""
        parts = CONTRACT_VERSION.split(".")
        assert len(parts) == 3, f"CONTRACT_VERSION {CONTRACT_VERSION!r} is not semver"
        for part in parts:
            assert part.isdigit(), f"Non-numeric component in {CONTRACT_VERSION!r}"

    def test_all_stamped_models_carry_same_version(self) -> None:
        """All models that stamp contract_version must use the same value."""
        state = CareerEngineState()
        msg = AgentMessage(sender="a", recipient="b", payload={}, payload_type="T")
        signal = UpgradeRequired(
            required_capability=Capability.SPEED_FAST, node_name="n", reason="r"
        )
        assert state.contract_version == CONTRACT_VERSION
        assert msg.contract_version == CONTRACT_VERSION
        assert signal.contract_version == CONTRACT_VERSION


# ── AccessMode (config) ───────────────────────────────────────────────────────


class TestAccessMode:
    """Tests for the AccessMode enum."""

    def test_access_mode_values(self) -> None:
        """FREE and BYOK must be the only two access modes."""
        values = {m.value for m in AccessMode}
        assert values == {"FREE", "BYOK"}

    def test_access_mode_is_str_enum(self) -> None:
        """AccessMode must be a str enum."""
        assert isinstance(AccessMode.FREE, str)
        assert str(AccessMode.FREE) == "FREE"
