"""Tests for the discovery graph: router brake + ADK workflow assembly (WS-A).

Acceptance criteria covered:
- discovery_router returns "user_checkpoint_node" at question_count==5,
  "execute_grill_turn_node" at 4 and 6, and "finalize_master_resume_node"
  when active_gaps is empty.
- build_discovery_workflow() assembles a real ADK Workflow with the expected
  nodes and routed edges.
- build_runner() returns a usable Runner wired to an in-memory session service.
"""

from __future__ import annotations

from typing import cast

from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, InMemorySessionService
from google.adk.workflow import Edge, Workflow

from schema import CareerEngineState, PhaseStatus
from workflows.discovery_graph import (
    build_discovery_workflow,
    build_runner,
    discovery_router,
)


def _edges(wf: Workflow) -> list[Edge]:
    """Return the workflow's edges narrowed to Edge instances (test helper)."""
    return [e for e in wf.edges if isinstance(e, Edge)]

# ── discovery_router (the 5-turn brake) ───────────────────────────────────────


class TestDiscoveryRouter:
    """The router implements the FROZEN 5-turn checkpoint brake."""

    def test_checkpoint_at_question_count_5(self) -> None:
        """At question_count==5 (mid-grill) the router forces a checkpoint."""
        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            active_gaps=["leadership"],
            question_count=5,
        )
        assert discovery_router(state) == "user_checkpoint_node"

    def test_grill_at_question_count_4(self) -> None:
        """At question_count==4 the router continues grilling."""
        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            active_gaps=["leadership"],
            question_count=4,
        )
        assert discovery_router(state) == "execute_grill_turn_node"

    def test_grill_at_question_count_6(self) -> None:
        """At question_count==6 the router continues grilling."""
        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            active_gaps=["leadership"],
            question_count=6,
        )
        assert discovery_router(state) == "execute_grill_turn_node"

    def test_finalize_when_active_gaps_empty(self) -> None:
        """With no active gaps remaining, the router finalizes."""
        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            active_gaps=[],
            question_count=3,
        )
        assert discovery_router(state) == "finalize_master_resume_node"

    def test_finalize_when_phase_complete(self) -> None:
        """A COMPLETE phase routes to finalize regardless of gaps."""
        state = CareerEngineState(
            current_phase=PhaseStatus.COMPLETE,
            active_gaps=["still_here"],
            question_count=2,
        )
        assert discovery_router(state) == "finalize_master_resume_node"

    def test_checkpoint_not_re_triggered_during_checkpoint_phase(self) -> None:
        """At question_count==5 but already in CHECKPOINT phase, do not loop checkpoint."""
        state = CareerEngineState(
            current_phase=PhaseStatus.CHECKPOINT,
            active_gaps=["leadership"],
            question_count=5,
        )
        # Brake suppressed during checkpoint phase -> continue grilling
        assert discovery_router(state) == "execute_grill_turn_node"

    def test_router_is_pure(self) -> None:
        """The router does not mutate its input and is deterministic."""
        state = CareerEngineState(
            current_phase=PhaseStatus.GRILLING,
            active_gaps=["x"],
            question_count=5,
        )
        snapshot = state.model_dump_json()
        r1 = discovery_router(state)
        r2 = discovery_router(state)
        assert r1 == r2
        assert state.model_dump_json() == snapshot


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
