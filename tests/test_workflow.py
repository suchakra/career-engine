"""Tests for the discovery graph: router brake + ADK workflow assembly — Phase 1.5.

Acceptance criteria covered:
- discovery_router returns "user_checkpoint_node" at question_count==5,
  "execute_grill_turn_node" at 4 and 6, and "finalize_master_resume_node"
  when no entries need work.
- build_discovery_workflow() assembles a real ADK Workflow with the expected
  nodes and routed edges.
- build_runner() returns a usable Runner wired to an in-memory session service.

v2.0.0 changes:
- Router uses work_timeline (entry status) instead of active_gaps.
- "No pending work" = all entries are grilled/summarized/skipped.
"""

from __future__ import annotations

from typing import cast

from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, InMemorySessionService
from google.adk.workflow import Edge, Workflow

from schema import CareerEngineState, Entry, EntryStatus, PhaseStatus
from workflows.discovery_graph import (
    build_discovery_workflow,
    build_runner,
    discovery_router,
)


def _edges(wf: Workflow) -> list[Edge]:
    """Return the workflow's edges narrowed to Edge instances (test helper)."""
    return [e for e in wf.edges if isinstance(e, Edge)]


def _entry_needing_work(start_date: str = "2022") -> Entry:
    """Build a test entry that needs quantifying."""
    return Entry(
        title="Test Role",
        start_date=start_date,
        status=EntryStatus.NEEDS_QUANTIFYING,
    )


def _entry_done(start_date: str = "2022") -> Entry:
    """Build a test entry that is already grilled (done)."""
    return Entry(
        title="Done Role",
        start_date=start_date,
        status=EntryStatus.GRILLED,
    )


# ── discovery_router (the 5-turn brake) ───────────────────────────────────────


class TestDiscoveryRouter:
    """The router implements the FROZEN 5-turn checkpoint brake (v2.0.0)."""

    def test_checkpoint_at_question_count_5(self) -> None:
        """At question_count==5 (mid-grill) the router forces a checkpoint."""
        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            work_timeline=[_entry_needing_work()],
            question_count=5,
        )
        assert discovery_router(state) == "user_checkpoint_node"

    def test_grill_at_question_count_4(self) -> None:
        """At question_count==4 the router continues grilling."""
        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            work_timeline=[_entry_needing_work()],
            question_count=4,
        )
        assert discovery_router(state) == "execute_grill_turn_node"

    def test_grill_at_question_count_6(self) -> None:
        """At question_count==6 the router continues grilling."""
        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            work_timeline=[_entry_needing_work()],
            question_count=6,
        )
        assert discovery_router(state) == "execute_grill_turn_node"

    def test_finalize_when_no_pending_work(self) -> None:
        """With no entries needing work, the router finalizes."""
        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            work_timeline=[_entry_done()],
            question_count=3,
        )
        assert discovery_router(state) == "finalize_master_resume_node"

    def test_finalize_when_empty_timeline(self) -> None:
        """With an empty timeline, the router finalizes (no pending work)."""
        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            work_timeline=[],
            question_count=3,
        )
        assert discovery_router(state) == "finalize_master_resume_node"

    def test_discovery_turn_when_coverage_set_and_unconfirmed(self) -> None:
        """No pending work + coverage boundary + unconfirmed → discovery turn (1.7-C)."""
        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            work_timeline=[_entry_done()],
            coverage_through="2022",
            coverage_confirmed=False,
            question_count=3,
        )
        assert discovery_router(state) == "discovery_turn_node"

    def test_finalize_when_coverage_confirmed(self) -> None:
        """Once the discovery turn is confirmed, no pending work → finalize."""
        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            work_timeline=[_entry_done()],
            coverage_through="2022",
            coverage_confirmed=True,
            question_count=3,
        )
        assert discovery_router(state) == "finalize_master_resume_node"

    def test_no_discovery_when_coverage_empty(self) -> None:
        """A present-role/text session (no coverage boundary) skips discovery."""
        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            work_timeline=[_entry_done()],
            coverage_through="",
            coverage_confirmed=False,
            question_count=3,
        )
        assert discovery_router(state) == "finalize_master_resume_node"

    def test_no_discovery_during_checkpoint_phase(self) -> None:
        """Discovery is suppressed while paused at a checkpoint."""
        state = CareerEngineState(
            current_phase=PhaseStatus.CHECKPOINT,
            work_timeline=[_entry_done()],
            coverage_through="2022",
            coverage_confirmed=False,
            question_count=3,
        )
        assert discovery_router(state) == "finalize_master_resume_node"

    def test_finalize_when_phase_complete(self) -> None:
        """A COMPLETE phase routes to finalize regardless of timeline."""
        state = CareerEngineState(
            current_phase=PhaseStatus.COMPLETE,
            work_timeline=[_entry_needing_work()],
            question_count=2,
        )
        assert discovery_router(state) == "finalize_master_resume_node"

    def test_checkpoint_not_re_triggered_during_checkpoint_phase(self) -> None:
        """At question_count==5 but already in CHECKPOINT phase, do not loop checkpoint."""
        state = CareerEngineState(
            current_phase=PhaseStatus.CHECKPOINT,
            work_timeline=[_entry_needing_work()],
            question_count=5,
        )
        # Brake suppressed during checkpoint phase -> continue grilling
        assert discovery_router(state) == "execute_grill_turn_node"

    def test_router_is_pure(self) -> None:
        """The router does not mutate its input and is deterministic."""
        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            work_timeline=[_entry_needing_work()],
            question_count=5,
        )
        snapshot = state.model_dump_json()
        r1 = discovery_router(state)
        r2 = discovery_router(state)
        assert r1 == r2
        assert state.model_dump_json() == snapshot

    def test_summarized_entries_count_as_done(self) -> None:
        """SUMMARIZED entries (soft horizon) are treated as done by the router."""
        entry = Entry(title="Old Role", start_date="2000", status=EntryStatus.SUMMARIZED)
        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            work_timeline=[entry],
            question_count=3,
        )
        # No pending work -> finalize
        assert discovery_router(state) == "finalize_master_resume_node"


# ── build_discovery_workflow ──────────────────────────────────────────────────


class TestBuildDiscoveryWorkflow:
    """The workflow builder assembles a real ADK Workflow with routed edges."""

    def test_returns_workflow_instance(self) -> None:
        """build_discovery_workflow returns a google.adk Workflow."""
        wf = build_discovery_workflow()
        assert isinstance(wf, Workflow)
        assert wf.name == "career_engine_discovery"

    def test_workflow_has_all_node_edges(self) -> None:
        """All five node names appear as edge endpoints, plus the router."""
        wf = build_discovery_workflow()
        node_names = set()
        for edge in _edges(wf):
            node_names.add(edge.from_node.name)
            node_names.add(edge.to_node.name)
        for expected in [
            "ingest_node",
            "discovery_router",
            "execute_grill_turn_node",
            "user_checkpoint_node",
            "discovery_turn_node",
            "finalize_master_resume_node",
            "tailor_node",
        ]:
            assert expected in node_names, f"{expected} missing from workflow edges"

    def test_router_branches_match_router_return_values(self) -> None:
        """The router's outgoing edge routes match discovery_router's return strings."""
        wf = build_discovery_workflow()
        router_routes = {
            edge.route
            for edge in _edges(wf)
            if edge.from_node.name == "discovery_router"
        }
        assert router_routes == {
            "execute_grill_turn_node",
            "user_checkpoint_node",
            "discovery_turn_node",
            "finalize_master_resume_node",
        }


# ── build_runner ──────────────────────────────────────────────────────────────


class TestBuildRunner:
    """The runner builder wires the workflow to a session service."""

    def test_returns_runner_with_default_session_service(self) -> None:
        """build_runner returns a Runner using an in-memory session service by default."""
        runner = build_runner()
        assert isinstance(runner, Runner)
        assert runner.app_name == "career_engine_discovery"

    def test_accepts_injected_session_service(self) -> None:
        """A caller-supplied session service is used as-is."""
        svc = cast(
            "BaseSessionService",
            InMemorySessionService(),  # type: ignore[no-untyped-call]
        )
        runner = build_runner(session_service=svc)
        assert isinstance(runner, Runner)
        assert runner.session_service is svc
