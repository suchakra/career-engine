"""Unit tests for the pure workflow node functions — Phase 1.5 (entry-based).

All model calls are mocked via set_model_client_factory — no live API calls.
Every test is deterministic.

Acceptance criteria covered:
- vague answer is REJECTED (asks for a metric; no validated StarStory committed)
- specific answer yields a StarStory with result populated + metrics_validated=True
  AND entry_id == frontier entry's UUID
- entry status is set to 'grilled' after a validated answer
- grill_frontier advances backward-chronologically as each entry is grilled
- grill_frontier is jumpable (setting it to an older entry makes that the target)
- already-quantified (documented + metric bullet) entries are skipped automatically
- soft horizon: entries >15y before reference_date are marked summarized
- discovery_turn_node appends a discovered entry from user reply
- checkpoint node does NOT commit/advance until checkpoint_verified is True
- REASONING_HIGH shortfall in FREE mode -> UpgradeRequired (typed), never raises
- each node is pure: same input -> same output, deps mocked, no external mutation
- _contains_real_metric: extended patterns for early-career / non-eng metrics
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
    Entry,
    EntryStatus,
    ExperienceType,
    PhaseStatus,
    StarStory,
    UpgradeRequired,
)
from workflows import nodes
from workflows.nodes import (
    _contains_real_metric,
    discovery_turn_node,
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


# ── Helpers for building test state ──────────────────────────────────────────

REF_DATE = "2026-06-29"


def _entry(
    title: str = "Senior Engineer",
    start_date: str = "2023",
    end_date: str = "2024",
    status: EntryStatus = EntryStatus.NEEDS_QUANTIFYING,
    org: str = "Acme",
) -> Entry:
    """Build a test Entry with given parameters."""
    return Entry(
        type=ExperienceType.FULL_TIME,
        title=title,
        org=org,
        start_date=start_date,
        end_date=end_date,
        status=status,
    )


# ── _contains_real_metric — engineering patterns ──────────────────────────────


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

    # ── Early-career / non-eng patterns ──────────────────────────────────────

    def test_users_metric_detected(self) -> None:
        """A user count counts as a metric."""
        assert _contains_real_metric("gained 1500 users in the first month") is True

    def test_downloads_metric_detected(self) -> None:
        """A download count counts as a metric."""
        assert _contains_real_metric("reached 10k downloads on PyPI") is True

    def test_github_stars_metric_detected(self) -> None:
        """GitHub stars count as a metric."""
        assert _contains_real_metric("project reached 500 stars on GitHub") is True

    def test_team_size_metric_detected(self) -> None:
        """Team size counts as a metric."""
        assert _contains_real_metric("led a team of 8 engineers") is True

    def test_team_size_alt_form_detected(self) -> None:
        """Alternative team size phrasing counts as a metric."""
        assert _contains_real_metric("managed a 6-person team across 3 time zones") is True

    def test_competition_rank_detected(self) -> None:
        """Competition placement counts as a metric."""
        assert _contains_real_metric("ranked in top 5 out of 200 teams") is True
        assert _contains_real_metric("finished 2nd place in the hackathon") is True

    def test_dataset_scale_detected(self) -> None:
        """Dataset scale counts as a metric."""
        assert _contains_real_metric("trained on 50k samples from the dataset") is True

    def test_citations_metric_detected(self) -> None:
        """Academic citations count as a metric."""
        assert _contains_real_metric("paper cited 12 times in first year") is True

    def test_gpa_metric_detected(self) -> None:
        """GPA counts as a metric."""
        assert _contains_real_metric("graduated with GPA of 3.9/4.0") is True
        assert _contains_real_metric("maintained 3.85 GPA throughout program") is True


# ── execute_grill_turn_node — vague answer rejected ───────────────────────────


class TestGrillVagueAnswerRejected:
    """A vague answer must be REJECTED: a follow-up is asked, no story committed."""

    def test_vague_answer_does_not_commit_story(self) -> None:
        """'I improved performance a lot' -> no validated StarStory; metric demanded."""
        entry = _entry()
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
            work_timeline=[entry],
            grill_frontier=str(entry.entry_id),
            reference_date=REF_DATE,
            pending_user_answer="I improved performance a lot",
        )
        result = execute_grill_turn_node(state)

        assert isinstance(result, CareerEngineState)
        # No story committed
        assert result.extracted_star_stories == []
        # Entry NOT marked as grilled
        timeline_entry = result.work_timeline[0]
        assert timeline_entry.status == EntryStatus.NEEDS_QUANTIFYING
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
        entry = _entry()
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
            work_timeline=[entry],
            grill_frontier=str(entry.entry_id),
            pending_user_answer="made it much faster overall",
        )
        result = execute_grill_turn_node(state)

        assert isinstance(result, CareerEngineState)
        # The regex gate overrides the model's false claim -> no story
        assert result.extracted_star_stories == []
        # Entry NOT grilled
        assert result.work_timeline[0].status == EntryStatus.NEEDS_QUANTIFYING
        # Answer consumed; a follow-up question surfaced
        assert result.pending_user_answer == ""
        assert result.current_question != ""


# ── execute_grill_turn_node — Free-Mode Pro-escalation gate ───────────────────


class TestGrillProEscalationGate:
    """After too many failed Flash+CoT attempts on an entry, Free Mode escalates."""

    _VAGUE_EXTRACTION = json.dumps(
        {
            "situation": "s",
            "task": "t",
            "action": "a",
            "result": "we improved things a lot",
            "metrics_found": False,
            "metric_summary": "",
        }
    )

    def _vague_client(self) -> ScriptedClient:
        return ScriptedClient(
            responses={
                "data extraction assistant": self._VAGUE_EXTRACTION,
                "senior engineering colleague": "Can you put a concrete number on that?",
            }
        )

    def test_escalates_after_threshold_failed_attempts_in_free_mode(self) -> None:
        """The failed attempt that reaches the threshold returns UpgradeRequired."""
        entry = _entry()
        _install_client(self._vague_client())
        # Pre-seed one below the threshold; this vague answer trips it.
        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            work_timeline=[entry],
            grill_frontier=str(entry.entry_id),
            pending_user_answer="we improved things a lot",
            grill_attempts={str(entry.entry_id): nodes._MAX_FLASH_GRILL_ATTEMPTS - 1},
        )
        result = execute_grill_turn_node(state)

        assert isinstance(result, UpgradeRequired)
        assert result.required_capability == Capability.REASONING_HIGH
        assert result.node_name == "execute_grill_turn_node"

    def test_below_threshold_keeps_probing_and_increments_counter(self) -> None:
        """Under the threshold: a follow-up is asked and the counter increments."""
        entry = _entry()
        _install_client(self._vague_client())
        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            work_timeline=[entry],
            grill_frontier=str(entry.entry_id),
            pending_user_answer="we improved things a lot",
            grill_attempts={str(entry.entry_id): 2},
        )
        result = execute_grill_turn_node(state)

        assert isinstance(result, CareerEngineState)
        assert result.grill_attempts[str(entry.entry_id)] == 3
        assert result.current_question != ""

    def test_byok_mode_does_not_escalate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """In BYOK mode REASONING_HIGH is already Pro — never escalate, keep probing."""
        from config import Settings

        monkeypatch.setattr(
            nodes, "get_settings", lambda: Settings(access_mode=AccessMode.BYOK)
        )
        entry = _entry()
        _install_client(self._vague_client())
        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            work_timeline=[entry],
            grill_frontier=str(entry.entry_id),
            pending_user_answer="we improved things a lot",
            grill_attempts={str(entry.entry_id): nodes._MAX_FLASH_GRILL_ATTEMPTS + 3},
        )
        result = execute_grill_turn_node(state)

        assert isinstance(result, CareerEngineState)  # no escalation despite high count
        assert result.current_question != ""

    def test_validated_answer_resets_entry_counter(self) -> None:
        """A validated metric clears that entry's failed-attempt counter."""
        entry = _entry()
        client = ScriptedClient(
            responses={
                "data extraction assistant": json.dumps(
                    {
                        "situation": "s",
                        "task": "t",
                        "action": "a",
                        "result": "cut p99 from 800ms to 120ms across 40 services",
                        "metrics_found": True,
                        "metric_summary": "p99 800->120ms",
                    }
                ),
            }
        )
        _install_client(client)
        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            work_timeline=[entry],
            grill_frontier=str(entry.entry_id),
            pending_user_answer="cut p99 from 800ms to 120ms across 40 services",
            grill_attempts={str(entry.entry_id): 3},
        )
        result = execute_grill_turn_node(state)

        assert isinstance(result, CareerEngineState)
        assert len(result.extracted_star_stories) == 1
        assert str(entry.entry_id) not in result.grill_attempts


# ── execute_grill_turn_node — specific answer accepted ────────────────────────


class TestGrillSpecificAnswerAccepted:
    """A specific, metric-rich answer must produce a validated StarStory."""

    def test_specific_answer_yields_validated_story(self) -> None:
        """'cut p99 from 800ms to 120ms across 40 services' -> validated StarStory."""
        entry = _entry()
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
                        "pillar": "performance_engineering",
                    }
                ),
            }
        )
        _install_client(client)

        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            work_timeline=[entry],
            grill_frontier=str(entry.entry_id),
            pending_user_answer=answer,
        )
        result = execute_grill_turn_node(state)

        assert isinstance(result, CareerEngineState)
        assert len(result.extracted_star_stories) == 1
        story = result.extracted_star_stories[0]
        assert isinstance(story, StarStory)
        assert story.result == answer
        assert story.metrics_validated is True
        assert story.entry_id == str(entry.entry_id)
        # Entry marked as grilled
        assert result.work_timeline[0].status == EntryStatus.GRILLED
        # The committed answer is cleared from the pending buffer
        assert result.pending_user_answer == ""
        assert result.checkpoint_delta_summary == ""

    def test_opening_question_when_no_pending_answer(self) -> None:
        """With no pending answer, the node generates an opening question."""
        entry = _entry()
        client = ScriptedClient(
            responses={
                "senior engineering colleague": (
                    "Tell me about a project where you drove real impact here."
                )
            }
        )
        _install_client(client)

        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            work_timeline=[entry],
            grill_frontier=str(entry.entry_id),
            pending_user_answer="",
        )
        result = execute_grill_turn_node(state)

        assert isinstance(result, CareerEngineState)
        assert result.extracted_star_stories == []
        # Opening question surfaced via the dedicated current_question field
        assert result.current_question != ""
        assert result.checkpoint_delta_summary == ""
        assert result.question_count == 1

    def test_frontier_advances_after_grilling(self) -> None:
        """After grilling entry A, the frontier advances to entry B (next ungrilled)."""
        entry_a = Entry(
            type=ExperienceType.FULL_TIME,
            title="Role A",
            org="Acme",
            start_date="2024",
            status=EntryStatus.NEEDS_QUANTIFYING,
        )
        entry_b = Entry(
            type=ExperienceType.FULL_TIME,
            title="Role B",
            org="Acme",
            start_date="2022",
            status=EntryStatus.NEEDS_QUANTIFYING,
        )
        answer = "cut p99 from 800ms to 120ms"
        client = ScriptedClient(
            responses={
                "data extraction assistant": json.dumps(
                    {
                        "result": answer,
                        "metrics_found": True,
                        "pillar": "perf",
                    }
                ),
            }
        )
        _install_client(client)

        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            work_timeline=[entry_a, entry_b],
            grill_frontier=str(entry_a.entry_id),
            pending_user_answer=answer,
        )
        result = execute_grill_turn_node(state)

        assert isinstance(result, CareerEngineState)
        # entry_a is now grilled
        grilled = next(e for e in result.work_timeline if str(e.entry_id) == str(entry_a.entry_id))
        assert grilled.status == EntryStatus.GRILLED
        # Frontier should now point to entry_b
        assert result.grill_frontier == str(entry_b.entry_id)


# ── Backward-chronological frontier and jumpable frontier ─────────────────────


class TestFrontierBehavior:
    """The grill frontier advances newest-first and is jumpable."""

    def test_backward_frontier_advances_newest_first(self) -> None:
        """With 3 entries (2024/2021/2018), frontier advances newest-first."""
        e2024 = Entry(title="2024 Role", start_date="2024", status=EntryStatus.NEEDS_QUANTIFYING)
        e2021 = Entry(title="2021 Role", start_date="2021", status=EntryStatus.NEEDS_QUANTIFYING)
        e2018 = Entry(title="2018 Role", start_date="2018", status=EntryStatus.NEEDS_QUANTIFYING)

        answer = "cut p99 from 800ms to 120ms"
        client = ScriptedClient(
            responses={
                "data extraction assistant": json.dumps(
                    {"result": answer, "metrics_found": True, "pillar": "perf"}
                )
            }
        )
        _install_client(client)

        # Start: grill 2024
        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            work_timeline=[e2024, e2021, e2018],
            grill_frontier=str(e2024.entry_id),
            pending_user_answer=answer,
            reference_date=REF_DATE,
        )
        result = execute_grill_turn_node(state)
        assert isinstance(result, CareerEngineState)
        # Frontier now points to 2021 (next newest)
        assert result.grill_frontier == str(e2021.entry_id)

        # Grill 2021
        state2 = result.model_copy(
            update={"pending_user_answer": answer, "grill_frontier": str(e2021.entry_id)}
        )
        result2 = execute_grill_turn_node(state2)
        assert isinstance(result2, CareerEngineState)
        # Frontier now points to 2018
        assert result2.grill_frontier == str(e2018.entry_id)

    def test_jumpable_frontier(self) -> None:
        """Setting grill_frontier to an older entry makes that entry the next grill target."""
        e2024 = Entry(title="2024 Role", start_date="2024", status=EntryStatus.GRILLED)
        e2021 = Entry(title="2021 Role", start_date="2021", status=EntryStatus.GRILLED)
        e2018 = Entry(title="2018 Role", start_date="2018", status=EntryStatus.NEEDS_QUANTIFYING)

        answer = "cut p99 from 800ms to 120ms"
        client = ScriptedClient(
            responses={
                "data extraction assistant": json.dumps(
                    {"result": answer, "metrics_found": True, "pillar": "perf"}
                )
            }
        )
        _install_client(client)

        # Jump directly to 2018
        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            work_timeline=[e2024, e2021, e2018],
            grill_frontier=str(e2018.entry_id),  # explicit jump
            pending_user_answer=answer,
            reference_date=REF_DATE,
        )
        result = execute_grill_turn_node(state)
        assert isinstance(result, CareerEngineState)
        # 2018 entry should now be grilled
        e2018_after = next(e for e in result.work_timeline if str(e.entry_id) == str(e2018.entry_id))
        assert e2018_after.status == EntryStatus.GRILLED
        # frontier empty (no more needs-work entries)
        assert result.grill_frontier == ""


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

        entry = _entry()
        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            work_timeline=[entry],
            grill_frontier=str(entry.entry_id),
            pending_user_answer="some answer",
        )
        result = execute_grill_turn_node(state)

        assert isinstance(result, UpgradeRequired)
        assert result.required_capability == Capability.REASONING_HIGH

    def test_reasoning_shortfall_does_not_raise(self) -> None:
        """The shortfall path must not raise any exception."""
        set_registry(_NoReasoningRegistry())
        _install_client(ScriptedClient(default="{}"))

        entry = _entry()
        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            work_timeline=[entry],
            grill_frontier=str(entry.entry_id),
            pending_user_answer="x",
        )
        # Should simply return, never raise
        result = execute_grill_turn_node(state)
        assert isinstance(result, UpgradeRequired)


# ── Already-quantified entry is skipped ──────────────────────────────────────


class TestAlreadyQuantifiedSkipped:
    """An entry with metric bullets should be skipped (not re-asked)."""

    def test_already_quantified_entry_marked_grilled_at_ingest(self) -> None:
        """An entry with metric bullet is marked grilled during ingest, not re-asked."""
        client = ScriptedClient(
            responses={
                "structured timeline": json.dumps(
                    {
                        "timeline": [
                            {
                                "type": "full_time",
                                "title": "Engineer",
                                "org": "Acme",
                                "start_date": "2022",
                                "end_date": "2024",
                                "bullets": ["Cut p99 from 800ms to 120ms across 40 services"],
                            }
                        ],
                        "summary": "Experienced engineer.",
                    }
                )
            }
        )
        _install_client(client)

        state = CareerEngineState(raw_history_text="10 years at Acme.")
        result = ingest_node(state)

        # The entry with a metric bullet should be auto-grilled
        assert result.work_timeline[0].status == EntryStatus.GRILLED
        # And NOT in the frontier (no more work to do)
        assert result.grill_frontier == ""


# ── Soft horizon ──────────────────────────────────────────────────────────────


class TestSoftHorizon:
    """Entries older than ~15 years before reference_date default to summarized."""

    def test_old_entry_marked_summarized_at_ingest(self) -> None:
        """An entry ending >15y before reference_date is marked summarized, not queued."""
        client = ScriptedClient(
            responses={
                "structured timeline": json.dumps(
                    {
                        "timeline": [
                            {
                                "type": "full_time",
                                "title": "Old Role",
                                "org": "OldCo",
                                "start_date": "2005",
                                "end_date": "2008",  # 18 years before 2026
                                "bullets": [],
                            }
                        ],
                        "summary": "Veteran engineer.",
                    }
                )
            }
        )
        _install_client(client)

        state = CareerEngineState(
            raw_history_text="Work history.",
            reference_date=REF_DATE,  # 2026-06-29
        )
        result = ingest_node(state)

        # 2008 is 18 years before 2026 -> soft horizon -> summarized
        assert result.work_timeline[0].status == EntryStatus.SUMMARIZED
        # Not in the grill queue
        assert result.grill_frontier == ""

    def test_recent_entry_not_soft_horizon(self) -> None:
        """An entry within 15 years of reference_date is NOT summarized."""
        client = ScriptedClient(
            responses={
                "structured timeline": json.dumps(
                    {
                        "timeline": [
                            {
                                "type": "full_time",
                                "title": "Recent Role",
                                "org": "Acme",
                                "start_date": "2018",
                                "end_date": "2022",  # 4 years before 2026
                                "bullets": [],
                            }
                        ],
                        "summary": "Engineer.",
                    }
                )
            }
        )
        _install_client(client)

        state = CareerEngineState(
            raw_history_text="Work history.",
            reference_date=REF_DATE,
        )
        result = ingest_node(state)

        # 2022 is 4 years before 2026 -> NOT soft horizon
        assert result.work_timeline[0].status == EntryStatus.NEEDS_QUANTIFYING


# ── discovery_turn_node ───────────────────────────────────────────────────────


class TestDiscoveryTurnNode:
    """discovery_turn_node confirms coverage and discovers new entries."""

    def test_discovery_appends_discovered_entry(self) -> None:
        """A user reply naming a new role appends an Entry(source='discovered')."""
        client = ScriptedClient(
            responses={
                "career coach": json.dumps(
                    {
                        "entries": [
                            {
                                "title": "ML Engineer",
                                "org": "StartupX",
                                "type": "full_time",
                                "start_date": "2024",
                                "end_date": "",
                            }
                        ]
                    }
                )
            }
        )
        _install_client(client)

        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            reference_date=REF_DATE,
            pending_user_answer="I've been working at StartupX as ML Engineer since 2024",
        )
        result = discovery_turn_node(state)

        assert isinstance(result, CareerEngineState)
        assert len(result.work_timeline) == 1
        new_entry = result.work_timeline[0]
        assert new_entry.source == "discovered"
        assert new_entry.status == EntryStatus.NEEDS_QUANTIFYING
        assert new_entry.title == "ML Engineer"
        assert result.pending_user_answer == ""

    def test_discovery_generates_question_when_no_answer(self) -> None:
        """Without a pending answer, the node generates a coverage question."""
        client = ScriptedClient(
            responses={
                "career coach": "What have you been working on since 2022?"
            }
        )
        _install_client(client)

        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            reference_date=REF_DATE,
            pending_user_answer="",
        )
        result = discovery_turn_node(state)

        assert result.current_question != ""
        assert result.work_timeline == []  # nothing added without an answer


# ── user_checkpoint_node — does not commit until verified ─────────────────────


class TestCheckpointNode:
    """The checkpoint (Hydration Point) must not advance until verified."""

    def test_checkpoint_summarizes_and_waits(self) -> None:
        """Unverified entry -> summary produced, phase=CHECKPOINT, NOT advanced."""
        entry = _entry(status=EntryStatus.GRILLED)
        client = ScriptedClient(
            responses={
                "summarizing progress": (
                    "You described cutting p99 latency 85%. Does that sound right?"
                )
            }
        )
        _install_client(client)

        story = StarStory(
            entry_id=str(entry.entry_id),
            pillar="performance_engineering",
            result="cut p99 from 800ms to 120ms",
            metrics_validated=True,
        )
        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            work_timeline=[entry],
            extracted_star_stories=[story],
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
        )
        result = user_checkpoint_node(state)

        assert result.current_phase == PhaseStatus.GRILLING
        assert result.checkpoint_verified is False
        assert result.checkpoint_delta_summary == ""


# ── ingest_node ───────────────────────────────────────────────────────────────


class TestIngestNode:
    """Ingest seeds work_timeline and moves the session into the grill phase."""

    def test_ingest_seeds_timeline(self) -> None:
        """Ingest parses history into work_timeline entries and sets phase=GRILLING."""
        client = ScriptedClient(
            responses={
                "structured timeline": json.dumps(
                    {
                        "timeline": [
                            {
                                "type": "full_time",
                                "title": "Senior Engineer",
                                "org": "Acme",
                                "start_date": "2020",
                                "end_date": "2024",
                                "bullets": [],
                            }
                        ],
                        "summary": "Senior engineer.",
                    }
                )
            }
        )
        _install_client(client)

        state = CareerEngineState(raw_history_text="20 years building distributed systems.")
        result = ingest_node(state)

        assert result.current_phase == PhaseStatus.GRILLING
        assert len(result.work_timeline) == 1
        assert result.work_timeline[0].title == "Senior Engineer"
        assert result.work_timeline[0].status == EntryStatus.NEEDS_QUANTIFYING
        assert result.grill_frontier == str(result.work_timeline[0].entry_id)

    def test_ingest_fallback_when_model_returns_nothing(self) -> None:
        """If the model returns no timeline, a generic fallback entry is seeded."""
        _install_client(ScriptedClient(default="not json at all"))

        state = CareerEngineState(raw_history_text="some history")
        result = ingest_node(state)

        assert result.current_phase == PhaseStatus.GRILLING
        assert len(result.work_timeline) == 1
        assert result.work_timeline[0].status == EntryStatus.NEEDS_QUANTIFYING

    def test_ingest_is_idempotent_when_timeline_exists(self) -> None:
        """If a timeline already exists, ingest does not re-seed it."""
        entry = _entry()
        client = ScriptedClient(default="should not be called")
        _install_client(client)

        state = CareerEngineState(
            current_phase=PhaseStatus.INGESTING,
            work_timeline=[entry],
        )
        result = ingest_node(state)

        # Should not have called the model
        assert client.calls == []
        # Timeline unchanged
        assert len(result.work_timeline) == 1
        assert result.work_timeline[0].entry_id == entry.entry_id
        assert result.current_phase == PhaseStatus.GRILLING


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

        entry = _entry(status=EntryStatus.GRILLED)
        story = StarStory(
            entry_id=str(entry.entry_id),
            pillar="delivery",
            result="cut deploy time from 45min to 3min",
            metrics_validated=True,
        )
        state = CareerEngineState(
            current_phase=PhaseStatus.FINALIZING,
            work_timeline=[entry],
            extracted_star_stories=[story],
        )
        result = finalize_master_resume_node(state)

        assert result.current_phase == PhaseStatus.COMPLETE
        # Structured resume written to its dedicated field
        assert result.master_resume_json != ""
        assert "achievements_by_pillar" in result.master_resume_json
        # Prose summary extracted for the PDF renderer
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
        # checkpoint_delta_summary is untouched
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

    def _grill_client(self) -> ScriptedClient:
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
                        "pillar": "perf",
                    }
                )
            }
        )

    def test_grill_is_deterministic(self) -> None:
        """Same input through grill twice -> equal output (modulo UUIDs)."""
        entry = _entry()
        _install_client(self._grill_client())
        base = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            work_timeline=[entry],
            grill_frontier=str(entry.entry_id),
            pending_user_answer="cut p99 from 800ms to 120ms",
        )
        r1 = execute_grill_turn_node(base.model_copy(deep=True))
        r2 = execute_grill_turn_node(base.model_copy(deep=True))
        assert isinstance(r1, CareerEngineState)
        assert isinstance(r2, CareerEngineState)
        # Compare ignoring auto-generated story_id/extracted_at timestamps
        s1 = r1.extracted_star_stories[0]
        s2 = r2.extracted_star_stories[0]
        assert s1.result == s2.result
        assert s1.metrics_validated == s2.metrics_validated
        assert s1.entry_id == s2.entry_id
        assert r1.question_count == r2.question_count

    def test_grill_does_not_mutate_input(self) -> None:
        """The input state object is not mutated by the node."""
        entry = _entry()
        _install_client(self._grill_client())
        original = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            work_timeline=[entry],
            grill_frontier=str(entry.entry_id),
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
                    "structured timeline": json.dumps(
                        {
                            "timeline": [
                                {"type": "full_time", "title": "Engineer", "org": "A",
                                 "start_date": "2020", "end_date": "2024", "bullets": []}
                            ],
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

    def test_no_datetime_now_in_nodes(self) -> None:
        """Nodes must not call datetime.now() — reference_date is injected externally."""
        import inspect

        import workflows.nodes as _nodes

        src = inspect.getsource(_nodes)
        assert "datetime.now()" not in src, (
            "Nodes must not call datetime.now() — use state.reference_date"
        )


# ── No-hardcoded-model assertion (capabilities requested via registry) ────────


class TestNoHardcodedModels:
    """Nodes must request models by capability, resolved through the registry."""

    def test_grill_requests_reasoning_high_model(self) -> None:
        """The grill node calls the model with the REASONING_HIGH-resolved model id."""
        entry = _entry()
        answer = "cut p99 from 800ms to 120ms"
        client = ScriptedClient(
            responses={
                "data extraction assistant": json.dumps(
                    {"result": answer, "metrics_found": True, "pillar": "perf"}
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
            work_timeline=[entry],
            grill_frontier=str(entry.entry_id),
            pending_user_answer=answer,
        )
        execute_grill_turn_node(state)

        assert isinstance(expected_model, str)
        assert client.calls, "model client was never called"
        assert all(c["model_id"] == expected_model for c in client.calls)
