"""Golden round-trip type tests for all Pydantic models — contract v2.0.0.

Every model is serialised with model_dump_json() and deserialised with
model_validate_json(), then asserted equal to the original.  This proves
that the schema contract survives the JSON boundary without data loss or
silent coercion.

v2.0.0 additions:
- Entry model round-trip (ExperienceType, EntryStatus).
- New CareerEngineState fields: work_timeline, coverage_through, reference_date,
  grill_frontier.
- REMOVED pillar fields (target_competencies, active_gaps, current_pillar) —
  tests assert those are GONE from the model.
- StarStory.entry_id field.
- discovery_completeness() / recent_window_complete() deterministic helpers.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel

from config import CONTRACT_VERSION, AccessMode
from schema import (
    AgentMessage,
    Application,
    ApplicationStatus,
    Capability,
    CareerEngineState,
    Entry,
    EntryStatus,
    ExperienceType,
    PendingAction,
    PhaseStatus,
    SessionPreferences,
    StarStory,
    UpgradeRequired,
    UserProfile,
    UserWorkspace,
    discovery_completeness,
    recent_window_complete,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _roundtrip[M: BaseModel](model_instance: M) -> M:
    """Serialise and deserialise a Pydantic model; return the reconstructed instance."""
    cls = type(model_instance)
    json_str = model_instance.model_dump_json()
    return cls.model_validate_json(json_str)


# ── Entry (v2.0.0) ────────────────────────────────────────────────────────────


class TestEntryRoundTrip:
    """Round-trip tests for the new Entry model."""

    def test_minimal_entry(self) -> None:
        """A minimal Entry (only required title field) survives round-trip."""
        original = Entry(title="Senior Engineer")
        reconstructed = _roundtrip(original)
        assert original == reconstructed

    def test_full_entry(self) -> None:
        """A fully-populated Entry survives round-trip."""
        original = Entry(
            entry_id=uuid4(),
            type=ExperienceType.FULL_TIME,
            title="Staff Software Engineer",
            org="Acme Corp",
            start_date="2020-03",
            end_date="2024-01",
            source="resume",
            bullets=["Led a team of 8 engineers.", "Reduced p99 latency by 70%."],
            status=EntryStatus.GRILLED,
            highlighted=True,
        )
        reconstructed = _roundtrip(original)
        assert original == reconstructed
        assert reconstructed.highlighted is True

    def test_entry_with_empty_end_date_means_present(self) -> None:
        """Empty end_date is the 'present' sentinel and round-trips correctly."""
        entry = Entry(title="Current Role", end_date="")
        reconstructed = _roundtrip(entry)
        assert reconstructed.end_date == ""

    def test_entry_defaults(self) -> None:
        """Entry defaults are correct for a freshly created entry."""
        entry = Entry(title="Intern Project")
        assert entry.type == ExperienceType.OTHER
        assert entry.status == EntryStatus.NEEDS_QUANTIFYING
        assert entry.source == "manual"
        assert entry.bullets == []
        assert entry.org == ""
        assert entry.highlighted is False

    def test_all_experience_types_roundtrip(self) -> None:
        """All ExperienceType values survive round-trip."""
        for exp_type in ExperienceType:
            entry = Entry(title="test", type=exp_type)
            reconstructed = _roundtrip(entry)
            assert reconstructed.type == exp_type

    def test_all_entry_statuses_roundtrip(self) -> None:
        """All EntryStatus values survive round-trip."""
        for status in EntryStatus:
            entry = Entry(title="test", status=status)
            reconstructed = _roundtrip(entry)
            assert reconstructed.status == status

    def test_all_source_literals_roundtrip(self) -> None:
        """All source literal values survive round-trip."""
        for source in ("resume", "discovered", "manual"):
            entry = Entry(title="test", source=source)
            reconstructed = _roundtrip(entry)
            assert reconstructed.source == source

    def test_entry_education_type(self) -> None:
        """Education-type entries round-trip and carry the right type."""
        entry = Entry(
            type=ExperienceType.EDUCATION,
            title="BS Computer Science",
            org="State University",
            start_date="2018",
            end_date="2022",
            status=EntryStatus.DOCUMENTED,
        )
        reconstructed = _roundtrip(entry)
        assert reconstructed.type == ExperienceType.EDUCATION
        assert reconstructed.org == "State University"


# ── StarStory (v2.0.0 — added entry_id) ──────────────────────────────────────


class TestStarStoryRoundTrip:
    """Round-trip tests for StarStory, including the new entry_id field."""

    def test_minimal_star_story(self) -> None:
        """A minimal StarStory (only required fields) survives round-trip."""
        original = StarStory(pillar="technical_leadership")
        reconstructed = _roundtrip(original)
        assert original == reconstructed

    def test_full_star_story(self) -> None:
        """A fully-populated StarStory survives round-trip."""
        original = StarStory(
            story_id=uuid4(),
            entry_id=str(uuid4()),
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

    def test_entry_id_defaults_to_empty(self) -> None:
        """entry_id defaults to empty string when not provided."""
        story = StarStory(pillar="leadership")
        assert story.entry_id == ""

    def test_entry_id_set_and_roundtrip(self) -> None:
        """entry_id set to a UUID string survives round-trip."""
        eid = str(uuid4())
        story = StarStory(pillar="delivery", entry_id=eid)
        reconstructed = _roundtrip(story)
        assert reconstructed.entry_id == eid

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


# ── CareerEngineState (v2.0.0) ────────────────────────────────────────────────


class TestCareerEngineStateRoundTrip:
    """Round-trip tests for CareerEngineState v2.0.0."""

    def test_default_state(self) -> None:
        """Default CareerEngineState (empty session) survives round-trip."""
        original = CareerEngineState()
        reconstructed = _roundtrip(original)
        assert original == reconstructed

    def test_state_with_work_timeline(self) -> None:
        """State with work_timeline entries survives round-trip."""
        entry = Entry(
            type=ExperienceType.FULL_TIME,
            title="Senior Engineer",
            org="Acme",
            start_date="2021",
            end_date="2024",
            status=EntryStatus.GRILLED,
        )
        story = StarStory(
            entry_id=str(entry.entry_id),
            pillar="delivery",
            result="Reduced deploy time from 45 min to 3 min.",
            metrics_validated=True,
        )
        original = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            work_timeline=[entry],
            grill_frontier=str(entry.entry_id),
            reference_date="2026-06-29",
            coverage_through="2024",
            extracted_star_stories=[story],
            question_count=3,
        )
        reconstructed = _roundtrip(original)
        assert original == reconstructed

    def test_state_carries_contract_version_280(self) -> None:
        """CareerEngineState must be stamped with CONTRACT_VERSION == "2.8.0"."""
        state = CareerEngineState()
        assert state.contract_version == CONTRACT_VERSION
        assert CONTRACT_VERSION == "2.8.0"

    def test_coverage_confirmed_defaults_false_and_roundtrips(self) -> None:
        """coverage_confirmed (v2.1.0) defaults to False and round-trips."""
        state = CareerEngineState()
        assert state.coverage_confirmed is False
        rt = _roundtrip(state.model_copy(update={"coverage_confirmed": True}))
        assert rt.coverage_confirmed is True

    def test_pillar_fields_are_gone(self) -> None:
        """v2.0.0 must NOT have target_competencies, active_gaps, current_pillar."""
        state = CareerEngineState()
        data = json.loads(state.model_dump_json())
        for removed_field in ("target_competencies", "active_gaps", "current_pillar"):
            assert removed_field not in data, (
                f"REMOVED field '{removed_field}' must not appear in CareerEngineState JSON"
            )
        # Also assert the model fields don't exist
        assert not hasattr(state, "target_competencies"), "target_competencies must be gone"
        assert not hasattr(state, "active_gaps"), "active_gaps must be gone"
        assert not hasattr(state, "current_pillar"), "current_pillar must be gone"

    def test_v200_new_fields_present_and_default(self) -> None:
        """New v2.0.0 fields are present with correct defaults."""
        state = CareerEngineState()
        assert state.work_timeline == []
        assert state.coverage_through == ""
        assert state.reference_date == ""
        assert state.grill_frontier == ""

    def test_reference_date_and_grill_frontier_roundtrip(self) -> None:
        """reference_date and grill_frontier survive round-trip."""
        eid = str(uuid4())
        state = CareerEngineState(
            reference_date="2026-06-29",
            grill_frontier=eid,
            coverage_through="2024-01",
        )
        reconstructed = _roundtrip(state)
        assert reconstructed.reference_date == "2026-06-29"
        assert reconstructed.grill_frontier == eid
        assert reconstructed.coverage_through == "2024-01"

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

    def test_v110_fields_carried_forward(self) -> None:
        """v1.1.0 conversational/output fields are still present in v2.0.0."""
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

    def test_state_with_nested_entry_and_star_story(self) -> None:
        """State with nested Entry + StarStory round-trips losslessly."""
        eid = uuid4()
        entry = Entry(
            entry_id=eid,
            type=ExperienceType.PROJECT,
            title="Open Source CLI",
            org="GitHub",
            start_date="2023-01",
            end_date="",
            source="discovered",
            bullets=["Built CLI with 500+ stars."],
            status=EntryStatus.GRILLED,
        )
        story = StarStory(
            entry_id=str(eid),
            pillar="open_source",
            result="500+ GitHub stars in 3 months.",
            metrics_validated=True,
        )
        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            work_timeline=[entry],
            extracted_star_stories=[story],
            grill_frontier=str(eid),
            reference_date="2026-06-29",
        )
        reconstructed = _roundtrip(state)
        assert reconstructed.work_timeline[0] == entry
        assert reconstructed.extracted_star_stories[0].entry_id == str(eid)


# ── discovery_completeness and recent_window_complete helpers ─────────────────


class TestDiscoveryCompletenessHelper:
    """Tests for the discovery_completeness() pure helper.

    All tests use a fixed reference_date for determinism — no datetime.now().
    """

    _REF_DATE = "2026-06-29"  # "now" for all tests in this class

    def _entry(
        self,
        end_date: str,
        status: EntryStatus = EntryStatus.NEEDS_QUANTIFYING,
    ) -> Entry:
        """Helper to build a test entry with given end_date and status."""
        return Entry(title="Test", end_date=end_date, status=status)

    def test_no_reference_date_returns_zero(self) -> None:
        """Without a reference_date the helper returns 0.0 (deterministic)."""
        state = CareerEngineState()
        assert discovery_completeness(state) == 0.0

    def test_empty_timeline_returns_zero(self) -> None:
        """An empty work_timeline returns 0.0."""
        state = CareerEngineState(reference_date=self._REF_DATE)
        assert discovery_completeness(state) == 0.0

    def test_all_entries_outside_window_returns_zero(self) -> None:
        """Entries older than 5 years before reference_date are not in the window."""
        # ref=2026, cutoff=2021, entry ended 2015 → not in window
        state = CareerEngineState(
            reference_date=self._REF_DATE,
            work_timeline=[self._entry("2015")],
        )
        assert discovery_completeness(state) == 0.0

    def test_present_entry_always_in_window(self) -> None:
        """An entry with empty end_date (present) is always in the window."""
        state = CareerEngineState(
            reference_date=self._REF_DATE,
            work_timeline=[self._entry("", status=EntryStatus.GRILLED)],
        )
        assert discovery_completeness(state) == 1.0

    def test_partial_completeness(self) -> None:
        """2 out of 4 grilled/summarized = 0.5."""
        entries = [
            self._entry("2024", EntryStatus.GRILLED),
            self._entry("2023", EntryStatus.SUMMARIZED),
            self._entry("2022", EntryStatus.NEEDS_QUANTIFYING),
            self._entry("2022", EntryStatus.DOCUMENTED),
        ]
        state = CareerEngineState(
            reference_date=self._REF_DATE,
            work_timeline=entries,
        )
        result = discovery_completeness(state)
        assert abs(result - 0.5) < 1e-9

    def test_all_grilled_returns_one(self) -> None:
        """All window entries grilled/summarized returns 1.0."""
        entries = [
            self._entry("2024", EntryStatus.GRILLED),
            self._entry("2023", EntryStatus.SUMMARIZED),
            self._entry("2022", EntryStatus.SKIPPED),
        ]
        state = CareerEngineState(
            reference_date=self._REF_DATE,
            work_timeline=entries,
        )
        assert discovery_completeness(state) == 1.0

    def test_skipped_counts_as_done(self) -> None:
        """SKIPPED status counts toward completeness (user chose to skip)."""
        state = CareerEngineState(
            reference_date=self._REF_DATE,
            work_timeline=[self._entry("2025", EntryStatus.SKIPPED)],
        )
        assert discovery_completeness(state) == 1.0

    def test_only_window_entries_counted(self) -> None:
        """Old entries (>5y) are excluded; only window entries are counted."""
        entries = [
            self._entry("2024", EntryStatus.GRILLED),   # in window
            self._entry("2020", EntryStatus.NEEDS_QUANTIFYING),  # just in window (2026-5=2021, 2020 is OUT)
            self._entry("2010", EntryStatus.NEEDS_QUANTIFYING),  # out of window
        ]
        state = CareerEngineState(
            reference_date=self._REF_DATE,
            work_timeline=entries,
        )
        # Only 2024 is in window (cutoff is 2021, 2020 is before that)
        result = discovery_completeness(state)
        assert result == 1.0  # 1/1 in-window entry is grilled


class TestRecentWindowCompleteHelper:
    """Tests for the recent_window_complete() pure helper.

    All tests use a fixed reference_date for determinism — no datetime.now().
    """

    _REF_DATE = "2026-06-29"

    def _entry(self, end_date: str, status: EntryStatus) -> Entry:
        """Helper to build a test entry with given end_date and status."""
        return Entry(title="Test", end_date=end_date, status=status)

    def test_no_reference_date_returns_false(self) -> None:
        """Without a reference_date the helper returns False."""
        state = CareerEngineState()
        assert recent_window_complete(state) is False

    def test_empty_timeline_returns_false(self) -> None:
        """An empty work_timeline is not complete."""
        state = CareerEngineState(reference_date=self._REF_DATE)
        assert recent_window_complete(state) is False

    def test_all_grilled_no_unprocessed_returns_true(self) -> None:
        """All window entries grilled and none needs_quantifying → complete."""
        state = CareerEngineState(
            reference_date=self._REF_DATE,
            work_timeline=[
                self._entry("2024", EntryStatus.GRILLED),
                self._entry("2023", EntryStatus.SUMMARIZED),
            ],
        )
        assert recent_window_complete(state) is True

    def test_has_unprocessed_returns_false(self) -> None:
        """A NEEDS_QUANTIFYING entry in the window means incomplete."""
        state = CareerEngineState(
            reference_date=self._REF_DATE,
            work_timeline=[
                self._entry("2024", EntryStatus.GRILLED),
                self._entry("2023", EntryStatus.NEEDS_QUANTIFYING),
            ],
        )
        assert recent_window_complete(state) is False

    def test_no_validated_entry_returns_false(self) -> None:
        """A window where no entry is GRILLED returns False (needs >= 1 validated)."""
        state = CareerEngineState(
            reference_date=self._REF_DATE,
            work_timeline=[
                self._entry("2024", EntryStatus.SUMMARIZED),
                self._entry("2023", EntryStatus.SKIPPED),
            ],
        )
        assert recent_window_complete(state) is False

    def test_present_entry_always_in_window(self) -> None:
        """A 'present' entry (empty end_date) counts in the window."""
        state = CareerEngineState(
            reference_date=self._REF_DATE,
            work_timeline=[self._entry("", EntryStatus.GRILLED)],
        )
        assert recent_window_complete(state) is True

    def test_documented_counts_as_unprocessed(self) -> None:
        """DOCUMENTED status is still unprocessed (needs quantifying)."""
        state = CareerEngineState(
            reference_date=self._REF_DATE,
            work_timeline=[
                self._entry("2024", EntryStatus.GRILLED),
                self._entry("2023", EntryStatus.DOCUMENTED),
            ],
        )
        assert recent_window_complete(state) is False


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

    def test_contract_version_is_280(self) -> None:
        """CONTRACT_VERSION must be exactly "2.8.0" (UserWorkspace.discovery_preferences additive bump)."""
        assert CONTRACT_VERSION == "2.8.0"

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
        assert UserProfile().contract_version == CONTRACT_VERSION
        assert UserWorkspace().contract_version == CONTRACT_VERSION
        assert SessionPreferences().contract_version == CONTRACT_VERSION


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


# ── ExperienceType and EntryStatus enums ──────────────────────────────────────


class TestExperienceTypeEnum:
    """Tests for ExperienceType enum."""

    def test_all_members_present(self) -> None:
        """All required ExperienceType values must be present."""
        values = {t.value for t in ExperienceType}
        expected = {
            "full_time", "internship", "project", "research",
            "open_source", "leadership", "part_time", "education", "other",
        }
        assert values == expected

    def test_is_str_enum(self) -> None:
        """ExperienceType must be a str enum."""
        assert isinstance(ExperienceType.FULL_TIME, str)


class TestEntryStatusEnum:
    """Tests for EntryStatus enum."""

    def test_all_members_present(self) -> None:
        """All required EntryStatus values must be present."""
        values = {s.value for s in EntryStatus}
        expected = {
            "documented", "needs_quantifying", "grilled", "summarized", "skipped"
        }
        assert values == expected

    def test_is_str_enum(self) -> None:
        """EntryStatus must be a str enum."""
        assert isinstance(EntryStatus.GRILLED, str)


# ── Application / PendingAction / UserWorkspace (v2.2.0) ──────────────────────


class TestWorkspaceRoundTrip:
    """Round-trip + stamping for the v2.2.0 application-tracking models."""

    def test_application_roundtrip(self) -> None:
        """An Application round-trips with status enum and dates preserved."""
        app = Application(
            company="Acme",
            job_title="Senior Engineer",
            status=ApplicationStatus.INTERVIEW,
            applied_on="2026-06-01",
            jd_text="...",
            tailored_resume_json='{"x": 1}',
        )
        rt = _roundtrip(app)
        assert rt == app
        assert rt.status is ApplicationStatus.INTERVIEW
        assert rt.applied_on == "2026-06-01"

    def test_pending_action_roundtrip(self) -> None:
        """A PendingAction round-trips and links to an application id."""
        pa = PendingAction(
            application_id="app-123",
            kind="follow_up",
            reason="Applied 14 days ago with no response.",
            created_on="2026-06-30",
        )
        rt = _roundtrip(pa)
        assert rt == pa
        assert rt.application_id == "app-123"

    def test_userworkspace_roundtrip_with_nested(self) -> None:
        """UserWorkspace round-trips with nested applications + pending actions."""
        ws = UserWorkspace(
            applications=[Application(company="Acme", applied_on="2026-06-01")],
            pending_actions=[PendingAction(application_id="x", created_on="2026-06-30")],
            profile=UserProfile(name="Ada", email="ada@x.io", links=["https://x/ada"]),
            discovery_preferences=SessionPreferences(target_roles=["Fractional CTO"]),
        )
        rt = _roundtrip(ws)
        assert rt == ws
        assert len(rt.applications) == 1
        assert len(rt.pending_actions) == 1
        assert rt.profile.name == "Ada" and rt.profile.links == ["https://x/ada"]
        assert rt.discovery_preferences.target_roles == ["Fractional CTO"]

    def test_userworkspace_is_contract_stamped(self) -> None:
        """UserWorkspace carries CONTRACT_VERSION like every persisted document."""
        assert UserWorkspace().contract_version == CONTRACT_VERSION

    def test_userworkspace_holds_no_identity(self) -> None:
        """Identity travels via context — no user_id field on the workspace model."""
        assert "user_id" not in UserWorkspace.model_fields

    def test_application_defaults_to_applied(self) -> None:
        """A new Application defaults to APPLIED status."""
        assert Application().status is ApplicationStatus.APPLIED
